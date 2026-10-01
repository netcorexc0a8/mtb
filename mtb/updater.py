"""Проверка новых релизов на GitHub и обновление бинарника из веб-интерфейса.

Проверка: раз в 6 часов (и по кнопке) — GET /repos/{MTB_REPO}/releases.
Результат хранится в базе (settings.update_state), веб читает его оттуда.

Обновление работает для установки через install.sh (бинарник под systemd):
  1. скачать mtb-linux-<arch> и SHA256SUMS нужного релиза, сверить хэш;
  2. запустить новый файл с --version и убедиться, что версия та;
  3. сохранить текущий бинарник как mtb.prev, атомарно заменить (os.replace);
  4. дождаться окончания идущего прогона и выйти — systemd (Restart=always)
     поднимет сервис уже с новым бинарником.
Для Docker и запуска из исходников интерфейс показывает команды обновления.
"""
from __future__ import annotations

import hashlib
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

from . import __version__

log = logging.getLogger("mtb.update")

REPO = os.environ.get("MTB_REPO", "netcorexc0a8/mtb")
API = os.environ.get("MTB_API_URL", "https://api.github.com").rstrip("/")   # GitHub Enterprise / зеркало
CHECK_INTERVAL_HOURS = 6
STATE_KEY = "update_state"
ARCH = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}


# ---------------------------------------------------------------- версии

def version_key(v: str) -> tuple:
    """Сравнение по semver: 0.1.0-dev < 0.1.0-rc.1 < 0.1.0 < 0.1.1.

    Понимает и нестрогие теги вида 0.0.1.dev; хвост git describe (-3-gabc) игнорирует.
    """
    v = v.strip().lstrip("v")
    v = re.sub(r"-\d+-g[0-9a-f]+(-dirty)?$|-dirty$", "", v)
    m = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?[.-]?(.*)$", v)
    if not m:
        return (0, 0, 0, 0, ())
    major, minor, patch = (int(x or 0) for x in m.groups()[:3])
    pre = m.group(4)
    if not pre:
        return (major, minor, patch, 1, ())
    parts = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"[.-]", pre) if p)
    return (major, minor, patch, 0, parts)


def is_prerelease(v: str) -> bool:
    return version_key(v)[3] == 0


def is_git_build(v: str = __version__) -> bool:
    return bool(re.search(r"-\d+-g[0-9a-f]+|-dirty$", v))


# ---------------------------------------------------------------- способ установки

def install_info() -> dict:
    """Как установлен mtb и можно ли обновить его из веба."""
    arch = ARCH.get(platform.machine().lower())
    if os.environ.get("MTB_RUNTIME") == "docker" or Path("/.dockerenv").exists():
        return {"type": "docker", "can_apply": False}
    if not getattr(sys, "frozen", False):
        return {"type": "source", "can_apply": False}
    exe = Path(sys.executable).resolve()
    info = {"type": "binary", "path": str(exe), "arch": arch, "can_apply": False}
    if sys.platform != "linux" or not arch:
        info["reason"] = f"платформа {sys.platform}/{platform.machine()} не поддерживается"
    elif not os.access(exe, os.W_OK) or not os.access(exe.parent, os.W_OK):
        info["reason"] = f"нет прав на запись в {exe.parent} — переустановите через install.sh"
    elif not os.environ.get("INVOCATION_ID"):
        info["reason"] = "сервис запущен не через systemd — перезапустить его некому"
    else:
        info["can_apply"] = True
    return info


# ---------------------------------------------------------------- проверка

def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Accept": "application/vnd.github+json", "User-Agent": f"mtb/{__version__}"})
    return s


def fetch_releases() -> list[dict]:
    r = _session().get(f"{API}/repos/{REPO}/releases", params={"per_page": 30}, timeout=15)
    if r.status_code == 403 and "rate limit" in r.text.lower():
        raise RuntimeError("GitHub: превышен лимит запросов, попробуйте позже")
    r.raise_for_status()
    return [x for x in r.json() if not x.get("draft")]


def resolve_channel(channel: str, current: str = __version__) -> bool:
    """True — учитывать пре-релизы."""
    if channel == "prerelease":
        return True
    if channel == "stable":
        return False
    return is_prerelease(current)          # auto: dev-версия ждёт dev-обновлений


def release_info(rel: dict) -> dict:
    return {
        "version": rel["tag_name"].lstrip("v"), "tag": rel["tag_name"], "url": rel.get("html_url"),
        "notes": (rel.get("body") or "")[:20000], "prerelease": bool(rel.get("prerelease")),
        "published_at": rel.get("published_at"),
        "assets": {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])},
    }


def find_release(version: str) -> dict:
    """Релиз по номеру версии (v0.2.3 или 0.2.3)."""
    tag = "v" + version.strip().lstrip("v")
    for rel in fetch_releases():
        if rel.get("tag_name") == tag:
            return release_info(rel)
    raise RuntimeError(f"релиз {tag} не найден в {REPO}")


def pick_latest(releases: list[dict], include_pre: bool) -> dict | None:
    best = None
    for rel in releases:
        tag = rel.get("tag_name", "")
        if not tag.startswith("v"):
            continue
        if (rel.get("prerelease") or is_prerelease(tag)) and not include_pre:
            continue
        if best is None or version_key(tag) > version_key(best["tag_name"]):
            best = rel
    return release_info(best) if best else None


def check(db, channel: str) -> dict:
    state = {"checked_at": time.time(), "channel": channel, "latest": None, "error": None}
    try:
        state["latest"] = pick_latest(fetch_releases(), resolve_channel(channel))
    except Exception as exc:  # noqa: BLE001 — сеть, API, закрытый контур
        state["error"] = f"{type(exc).__name__}: {exc}"[:300]
        prev = get_state(db)
        state["latest"] = prev.get("latest") if prev.get("channel") == channel else None
        log.warning("Проверка обновлений не удалась: %s", state["error"])
    db.set_settings({STATE_KEY: state})
    return state


def get_state(db) -> dict:
    return db.get_settings().get(STATE_KEY) or {}


def summary(db) -> dict:
    """Что показать в интерфейсе."""
    st = get_state(db)
    latest = st.get("latest")
    available = bool(latest) and version_key(latest["version"]) > version_key(__version__)
    return {"current": __version__, "available": available, "latest": latest,
            "checked_at": st.get("checked_at"), "error": st.get("error"), "repo": REPO,
            "releases_url": f"https://github.com/{REPO}/releases"}


# ---------------------------------------------------------------- обновление

def _download(url: str, dest: Path) -> str:
    h = hashlib.sha256()
    with _session().get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 16):
                fh.write(chunk)
                h.update(chunk)
    return h.hexdigest()


def apply(latest: dict) -> dict:
    """Обновление из веба: проверки установки, замена бинарника. Перезапуск — schedule_restart()."""
    info = install_info()
    if not info["can_apply"]:
        raise RuntimeError(info.get("reason") or "обновление из веба для этой установки недоступно")
    return install_binary(latest, Path(info["path"]), info["arch"])


def install_binary(latest: dict, exe: Path, arch: str, progress=None) -> dict:
    """Скачать бинарник релиза, сверить SHA256, проверить --version, сохранить .prev, заменить.

    Владелец и права файла сохраняются: при запуске от root бинарник остаётся
    за пользователем сервиса, и обновление из веба продолжит работать.
    """
    say = progress or (lambda msg: None)
    asset = f"mtb-linux-{arch}"
    assets = latest.get("assets") or {}
    if asset not in assets or "SHA256SUMS" not in assets:
        raise RuntimeError(f"в релизе {latest['tag']} нет {asset} или SHA256SUMS")

    st = exe.stat()
    tmp = exe.with_name(f".{exe.name}.new")
    try:
        say(f"Загрузка {asset} ({latest['tag']})…")
        sums = _session().get(assets["SHA256SUMS"], timeout=30)
        sums.raise_for_status()
        expected = next((ln.split()[0] for ln in sums.text.splitlines()
                         if ln.strip().endswith(asset)), None)
        if not expected:
            raise RuntimeError(f"в SHA256SUMS нет строки для {asset}")
        actual = _download(assets[asset], tmp)
        if actual != expected:
            raise RuntimeError("контрольная сумма не совпала — файл повреждён или подменён")
        say("Контрольная сумма совпала, проверка запуска…")
        tmp.chmod(0o755)
        out = subprocess.run([str(tmp), "--version"], capture_output=True, text=True, timeout=60,
                             env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
        reported = out.stdout.strip().split()[-1] if out.stdout.strip() else ""
        if out.returncode != 0 or version_key(reported) != version_key(latest["version"]):
            raise RuntimeError(f"новый бинарник не запустился или сообщил версию «{reported or out.stderr.strip()[:100]}»")
        prev = exe.with_name(exe.name + ".prev")
        shutil.copy2(exe, prev)
        if hasattr(os, "geteuid") and os.geteuid() == 0:      # сохранить владельца (пользователь сервиса)
            os.chown(tmp, st.st_uid, st.st_gid)
            os.chown(prev, st.st_uid, st.st_gid)
        os.replace(tmp, exe)
    finally:
        tmp.unlink(missing_ok=True)
    log.warning("Бинарник обновлён до %s (%s), предыдущий — %s.prev", latest["version"], exe, exe)
    return {"from": __version__, "to": latest["version"], "path": str(exe)}


def schedule_restart(run_lock: threading.Lock, delay: float = 1.5) -> None:
    """Дождаться окончания прогона и выйти: systemd поднимет новый бинарник."""
    def _go():
        time.sleep(delay)                   # дать ответу API уйти в браузер
        if not run_lock.acquire(timeout=3600):
            log.error("Прогон не закончился за час — перезапуск отменён, перезапустите сервис вручную")
            return
        log.warning("Перезапуск после обновления")
        logging.shutdown()
        os._exit(3)                         # ненулевой код: перезапуск и при Restart=on-failure
    threading.Thread(target=_go, name="restart", daemon=True).start()


def instructions(info: dict, latest: dict | None) -> dict:
    """Команды обновления для установок, которые не обновляются из веба."""
    tag = latest["tag"] if latest else "vX.Y.Z"
    pre = latest and latest.get("prerelease")
    base = f"https://github.com/{REPO}/releases/download/{tag}/install.sh"
    if info["type"] == "docker":
        image_tag = tag.lstrip("v") if pre else "latest"
        cmd = ("docker compose pull && docker compose up -d" if not pre else
               f"# в docker-compose.yml: image: ghcr.io/{REPO}:{image_tag}\ndocker compose pull && docker compose up -d")
        return {"commands": cmd}
    if info["type"] == "source":
        return {"commands": f"git fetch --tags && git checkout {tag}\npip install -r requirements.txt\n# перезапустите сервис"}
    return {"commands": f"curl -fsSL {base} | sh -s {tag}"}
