"""Хранение бэкапов в локальной папке BACKUP_DIR.

STORAGE=git (по умолчанию) — текущее состояние + история в git:
  по умолчанию        локальный git для истории изменений
  GIT_HISTORY=false   просто файлы, только последнее состояние
  GITEA_REPO_URL      то же + push в Gitea (git включается принудительно)

STORAGE=snapshots — отдельная папка с датой на каждый прогон + ротация:
  <device>/<YYYY-MM-DD_HHMMSS>/config.rsc, system.backup, meta.json, certs/…
  SNAPSHOT_RETENTION_DAYS  удалять снимки старше N дней (0 — не удалять)
  SNAPSHOT_KEEP_MIN        но всегда оставлять N последних
  SNAPSHOT_ON_CHANGE       создавать снимок, только если что-то изменилось

Раскладка STORAGE=git:
  <device>/config.rsc        экспорт с паролями, без строки с датой
  <device>/system.backup     обновляется только при изменении конфига
                             (нет при transport: api + api_binary: skip)
  <device>/meta.json         identity и версия RouterOS
  <device>/certs/index.json  все сертификаты: имя, CN, отпечаток, срок
  <device>/certs/*.p12       или *.crt + *.key (cert_format: pem);
                             обновляются только при изменении index.json

.backup, .p12 и зашифрованные .key при каждом экспорте получают новую соль, поэтому ежедневно
их перезаписывать бессмысленно — история росла бы без реальных изменений.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from .mikrotik import DeviceResult

log = logging.getLogger(__name__)

_HEADER_RE = re.compile(rb"^# .*? by RouterOS .*$", re.MULTILINE)


def normalize_export(data: bytes) -> bytes:
    data = data.replace(b"\r\n", b"\n")
    data = _HEADER_RE.sub(b"# by RouterOS", data, count=1)
    return data.rstrip(b"\n") + b"\n"


def make_storage(s, started: datetime):
    if s.storage == "snapshots":
        return SnapshotStorage(s, started)
    return GitStorage(s, started)


def _cert_files(d: Path) -> list[Path]:
    if not d.is_dir():
        return []
    return [p for p in d.iterdir() if p.is_file() and p.suffix in (".p12", ".crt", ".key")]


def _meta_json(res: DeviceResult) -> str:
    return json.dumps({"identity": res.identity, "version": res.version},
                      ensure_ascii=False, indent=2) + "\n"


def _index_json(res: DeviceResult) -> str:
    return json.dumps(res.cert_index, ensure_ascii=False, indent=2) + "\n"


def _read_text(p: Path) -> str | None:
    return p.read_text(encoding="utf-8") if p.exists() else None


class GitStorage:
    def __init__(self, s, started: datetime | None = None):
        self.path: Path = s.backup_dir
        self.remote = s.git_url
        self.use_git = s.git_history or bool(self.remote)
        self.branch = s.git_branch

        cfg = {"safe.directory": "*"}  # владелец bind-mount может отличаться от uid контейнера
        if self.remote:
            # Токен передаём через GIT_CONFIG_*, чтобы он не попал в .git/config и в ps
            auth = base64.b64encode(f"{s.git_user}:{s.git_token}".encode()).decode()
            cfg["http.extraHeader"] = f"Authorization: Basic {auth}"
            if s.git_ca:
                cfg["http.sslCAInfo"] = s.git_ca
            if s.git_insecure:
                cfg["http.sslVerify"] = "false"
        self.env = {
            **os.environ,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": s.git_author_name,
            "GIT_AUTHOR_EMAIL": s.git_author_email,
            "GIT_COMMITTER_NAME": s.git_author_name,
            "GIT_COMMITTER_EMAIL": s.git_author_email,
            "GIT_CONFIG_COUNT": str(len(cfg)),
        }
        for i, (k, v) in enumerate(cfg.items()):
            self.env[f"GIT_CONFIG_KEY_{i}"] = k
            self.env[f"GIT_CONFIG_VALUE_{i}"] = v
        if started is not None:
            # Дата коммита = время запуска прогона: по ней веб-интерфейс сортирует и фильтрует
            self.env["GIT_AUTHOR_DATE"] = self.env["GIT_COMMITTER_DATE"] = started.isoformat()

    # ------------------------------------------------------------ git

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        p = subprocess.run(["git", *args], cwd=self.path, env=self.env,
                           capture_output=True, text=True, timeout=300)
        if check and p.returncode != 0:
            raise RuntimeError(f"git {args[0]}: {p.stderr.strip()}")
        return p

    def _has_commits(self) -> bool:
        return self._git("rev-parse", "--verify", "HEAD", check=False).returncode == 0

    def prepare(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        if not self.use_git:
            return
        if shutil.which("git") is None:
            raise RuntimeError("git не установлен: установите git или задайте GIT_HISTORY=false "
                               "(для push в Gitea git обязателен)")
        if not (self.path / ".git").exists():
            self._git("init", "-q", "-b", self.branch)
            log.info("Инициализирован локальный git в %s", self.path)
        if not self.remote:
            return

        remotes = self._git("remote").stdout.split()
        self._git("remote", "set-url" if "origin" in remotes else "add", "origin", self.remote)
        self._git("fetch", "-q", "origin")
        remote_has_branch = bool(self._git("ls-remote", "--heads", "origin", self.branch).stdout.strip())
        if remote_has_branch and not self._has_commits():
            # новая локальная папка, в Gitea уже есть история — берём её
            self._git("checkout", "-q", "-B", self.branch, f"origin/{self.branch}")

    def commit(self, message: str, allow_empty: bool = False) -> bool:
        """allow_empty — для ручного бэкапа без изменений: он всё равно попадает в историю."""
        if not self.use_git:
            return False
        self._git("add", "-A")
        if not self._git("status", "--porcelain").stdout.strip():
            if not allow_empty:
                return False
            self._git("commit", "-q", "--allow-empty", "-m", message)
            log.info("Пустой коммит (ручной бэкап без изменений)")
            return True
        self._git("commit", "-q", "-m", message)
        log.info("Локальный коммит: %s", message.splitlines()[0])
        return True

    def push(self) -> bool:
        """Push в Gitea. Вызывается каждый прогон: догоняет неудачные прошлые push."""
        if not self.remote or not self._has_commits():
            return False
        p = self._git("push", "-q", "origin", f"HEAD:{self.branch}", check=False)
        if p.returncode != 0:
            log.warning("push отклонён, пробую rebase: %s", p.stderr.strip())
            self._git("pull", "-q", "--rebase", "origin", self.branch)
            self._git("push", "-q", "origin", f"HEAD:{self.branch}")
        log.info("Отправлено в Gitea (%s)", self.branch)
        return True

    # ------------------------------------------------------------ files

    def write(self, res: DeviceResult, kind: str = "scheduled", notes: str = "",
              force: bool = False) -> list[str]:
        """Записывает результат устройства, возвращает список изменений.

        Тип и заметка попадают в трейлеры коммита (runner._commit_message).
        """
        d = self.path / res.name
        (d / "certs").mkdir(parents=True, exist_ok=True)
        changes: list[str] = []

        cfg_path = d / "config.rsc"
        new_cfg = normalize_export(res.config)
        cfg_changed = not cfg_path.exists() or cfg_path.read_bytes() != new_cfg
        if cfg_changed:
            cfg_path.write_bytes(new_cfg)
            changes.append("config")

        bk_path = d / "system.backup"
        if res.backup and (cfg_changed or not bk_path.exists()):
            bk_path.write_bytes(res.backup)

        meta = _meta_json(res)
        meta_path = d / "meta.json"
        if not meta_path.exists() or meta_path.read_text(encoding="utf-8") != meta:
            meta_path.write_text(meta, encoding="utf-8")
            changes.append(f"RouterOS {res.version}")

        if res.config_only:            # сертификаты не собирались — не трогаем
            return changes

        idx = _index_json(res)
        idx_path = d / "certs" / "index.json"
        cert_files = _cert_files(d / "certs")
        if (not idx_path.exists() or idx_path.read_text(encoding="utf-8") != idx
                or {p.name for p in cert_files} != set(res.certs)):
            for p in cert_files:
                p.unlink()
            for fname, data in res.certs.items():
                (d / "certs" / fname).write_bytes(data)
            idx_path.write_text(idx, encoding="utf-8")
            changes.append("certs")

        return changes


class SnapshotStorage:
    """Папка с датой на каждый прогон и ротация старых снимков."""

    STAMP = "%Y-%m-%d_%H%M%S"
    STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}(-\d+)?$")

    def __init__(self, s, started: datetime):
        self.path: Path = s.backup_dir
        self.started = started.replace(tzinfo=None)
        self.stamp = started.strftime(self.STAMP)
        self.retention_days = s.snapshot_retention_days
        self.keep_min = max(1, s.snapshot_keep_min)
        self.on_change = s.snapshot_on_change
        self._written: list[str] = []

    def prepare(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)

    def snapshots(self, device: str) -> list[Path]:
        d = self.path / device
        if not d.is_dir():
            return []
        return sorted(p for p in d.iterdir() if p.is_dir() and self.STAMP_RE.match(p.name))

    def write(self, res: DeviceResult, kind: str = "scheduled", notes: str = "",
              force: bool = False) -> list[str]:
        prev = (self.snapshots(res.name) or [None])[-1]
        new_cfg = normalize_export(res.config)
        changes: list[str] = []

        prev_cfg = prev / "config.rsc" if prev else None
        if not prev_cfg or not prev_cfg.exists() or normalize_export(prev_cfg.read_bytes()) != new_cfg:
            changes.append("config")
        if not prev or _read_text(prev / "meta.json") != _meta_json(res):
            changes.append(f"RouterOS {res.version}")
        if not res.config_only and (not prev or _read_text(prev / "certs" / "index.json") != _index_json(res)):
            changes.append("certs")

        if self.on_change and prev and not changes and not force:
            return []

        snap = self.path / res.name / self.stamp
        n = 1
        while snap.exists():
            snap = self.path / res.name / f"{self.stamp}-{n}"
            n += 1
        snap.mkdir(parents=True)
        (snap / "config.rsc").write_bytes(res.config.replace(b"\r\n", b"\n"))
        (snap / "meta.json").write_text(_meta_json(res), encoding="utf-8")
        (snap / "info.json").write_text(json.dumps(
            {"type": kind, "notes": notes, "created": self.started.isoformat()},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if res.backup:
            (snap / "system.backup").write_bytes(res.backup)
        if not res.config_only:
            (snap / "certs").mkdir()
            (snap / "certs" / "index.json").write_text(_index_json(res), encoding="utf-8")
            for fname, data in res.certs.items():
                (snap / "certs" / fname).write_bytes(data)
        self._written.append(res.name)
        log.info("%s: снимок %s", res.name, snap.name)
        return changes

    def prune(self, device: str) -> int:
        if self.retention_days <= 0:
            return 0
        snaps = self.snapshots(device)
        border = self.started - timedelta(days=self.retention_days)
        removed = 0
        for snap in snaps[:-self.keep_min]:
            try:
                taken = datetime.strptime(snap.name[:17], self.STAMP)
            except ValueError:
                continue
            if taken < border:
                shutil.rmtree(snap)
                removed += 1
        if removed:
            log.info("%s: удалено старых снимков: %d", device, removed)
        return removed

    def commit(self, message: str, allow_empty: bool = False) -> bool:
        for device in self._written:
            self.prune(device)
        return bool(self._written)

    def push(self) -> bool:
        return False


def rename_device_dir(s, old: str, new: str) -> str | None:
    """Переносит бэкапы устройства в папку с новым именем.

    git: `git mv` отдельным коммитом с трейлером Type: rename — история
    сохраняется, старые коммиты остаются под прежним путём (веб показывает их
    под новым именем через псевдоним). Снимки и «только текущее» — переименование
    папки. Возвращает описание сделанного или None, если бэкапов ещё не было.
    """
    src, dst = s.backup_dir / old, s.backup_dir / new
    if not src.exists():
        return None
    if dst.exists():
        raise ValueError(f"Папка бэкапов {new} уже существует")
    if s.storage == "git" and (s.backup_dir / ".git").exists() and shutil.which("git"):
        store = GitStorage(s)
        store._git("mv", old, new)
        store._git("commit", "-q", "-m",
                   f"rename {old} → {new}\n\nType: rename\nDevices: {new}\nRenamed-From: {old}")
        try:
            store.push()
        except Exception as exc:  # noqa: BLE001 — догонит следующий прогон
            log.warning("push после переименования не удался: %s", exc)
        return "git mv"
    src.rename(dst)
    return "rename"
