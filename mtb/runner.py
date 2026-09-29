"""Один прогон бэкапа. Вызывается планировщиком, командой run и веб-интерфейсом."""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config
from .mikrotik import backup_device
from .notify import telegram
from .storage import make_storage

log = logging.getLogger("mtb")

# Прогоны не должны пересекаться: общий git-репозиторий и общие файлы на роутерах
RUN_LOCK = threading.Lock()


@dataclass
class RunResult:
    started: datetime
    ok: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    changed: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.failed


def _commit_message(started: datetime, kind: str, notes: str, devices: list[str],
                    changed: dict[str, list[str]]) -> str:
    if kind == "manual":
        subject = f"manual backup {', '.join(devices)} {started:%Y-%m-%d %H:%M}"
    else:
        subject = f"backup {started:%Y-%m-%d %H:%M}"
    lines = [f"{n}: {', '.join(c)}" for n, c in sorted(changed.items())]
    trailers = [f"Type: {kind}", f"Devices: {','.join(sorted(devices))}"]
    if notes:
        trailers.append("Notes: " + " ".join(notes.split()))
    body = "\n".join(lines)
    return subject + "\n\n" + (body + "\n\n" if body else "") + "\n".join(trailers)


def run_once(s: config.Settings, only: list[str] | None = None, kind: str = "scheduled",
             notes: str = "", notify: bool = True, db=None, user: str | None = None) -> RunResult:
    """only — имена устройств; без only берутся только включённые (enabled)."""
    with RUN_LOCK:
        devices = [d for d in s.devices if d.name in only] if only else [d for d in s.devices if d.enabled]
        run_id = _journal_start(db, kind, user, devices)
        result = _run(s, devices, kind, notes, notify)
        _journal_finish(db, run_id, result)
        return result


def _journal_start(db, kind, user, devices) -> int | None:
    if db is None:
        return None
    with db.tx() as c:
        cur = c.execute("INSERT INTO runs(started_at, kind, user, devices) VALUES(?,?,?,?)",
                        (time.time(), kind, user, json.dumps([d.name for d in devices])))
        return cur.lastrowid


def _journal_finish(db, run_id, r: "RunResult") -> None:
    if db is None or run_id is None:
        return
    with db.tx() as c:
        c.execute("UPDATE runs SET finished_at=?, ok=?, failed=?, changed=?, warnings=? WHERE id=?",
                  (time.time(), json.dumps(r.ok), json.dumps(r.failed, ensure_ascii=False),
                   json.dumps(r.changed, ensure_ascii=False), json.dumps(r.warnings, ensure_ascii=False),
                   run_id))
        c.execute("DELETE FROM runs WHERE started_at < ?", (time.time() - 365 * 86400,))


def _run(s, devices, kind, notes, notify) -> RunResult:
    only = [d.name for d in devices]
    tz = ZoneInfo(s.timezone)
    started = datetime.now(tz)
    result = RunResult(started)
    manual = kind == "manual"
    store = make_storage(s, started)

    try:
        store.prepare()
    except Exception as exc:
        log.exception("Ошибка подготовки хранилища")
        result.failed["storage"] = str(exc)
        if notify:
            telegram(s.tg_token, s.tg_chat, f"❌ mtb: ошибка хранилища {s.backup_dir}: {exc}")
        return result

    if not devices:
        result.warnings.append("нет включённых устройств")
        return result
    if not s.backup_passphrase and any(not d.config_only for d in devices):
        result.failed["settings"] = "Не задан пароль шифрования бэкапов (Настройки → Хранение)"
        return result

    known_hosts = s.data_dir / "known_hosts"
    with ThreadPoolExecutor(max_workers=s.workers) as pool:
        futures = {pool.submit(backup_device, d, s.backup_passphrase, known_hosts): d for d in devices}
        for fut in as_completed(futures):
            dev = futures[fut]
            try:
                res = fut.result()
                ch = store.write(res, kind=kind, notes=notes, force=manual)
                result.ok.append(dev.name)
                if ch:
                    result.changed[dev.name] = ch
                log.info("%s: готово%s", dev.name, f" (изменено: {', '.join(ch)})" if ch else "")
            except Exception as exc:
                result.failed[dev.name] = f"{type(exc).__name__}: {exc}"
                log.error("%s: ошибка: %s", dev.name, result.failed[dev.name])

    if result.ok:
        try:
            store.commit(_commit_message(started, kind, notes, result.ok, result.changed),
                         allow_empty=manual)
        except Exception as exc:
            log.exception("Ошибка хранилища")
            result.warnings.append(f"{'git commit' if s.storage == 'git' else 'ротация снимков'}: {exc}")
    try:
        store.push()
    except Exception as exc:
        log.error("Ошибка push в Gitea: %s", exc)
        result.warnings.append(f"push в Gitea: {exc}")

    icon = "✅" if not (result.failed or result.warnings) else ("⚠️" if result.ok else "❌")
    title = "ручной бэкап" if manual else "mtb"
    report = [f"{icon} {title} {started:%d.%m %H:%M}: {len(result.ok)}/{len(devices)} успешно"]
    if result.changed:
        report.append("Изменения: " + "; ".join(
            f"{n} ({', '.join(c)})" for n, c in sorted(result.changed.items())))
    for n, e in sorted(result.failed.items()):
        report.append(f"• {n}: {e}")
    for w in result.warnings:
        report.append(f"• {w}")
    text = "\n".join(report)
    log.info(text.replace("\n", " | "))

    # Уведомляем при ошибках или изменениях; «всё без изменений» — только в лог
    if notify and (result.failed or result.warnings or result.changed):
        telegram(s.tg_token, s.tg_chat, text)

    if not result.failed and not manual:
        (s.data_dir / "last_success").write_text(datetime.now(tz).isoformat())
    return result
