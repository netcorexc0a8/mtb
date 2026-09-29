"""Перенос старой конфигурации (devices.yaml + .env) в базу.

  mtb import-config --config config/devices.yaml --env-file .env [--replace]

Пароли берутся из переменных, как раньше: MT_PASSWORD или password_env устройства.
tls_ca и GITEA_CA_FILE — пути к PEM: читается содержимое файла.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from .config import ConfigError, save_device, update_settings
from .db import Database
from .secretbox import SecretBox

ENV_MAP = {
    "SCHEDULE": "schedule", "TZ": "timezone", "WORKERS": "workers",
    "BACKUP_PASSPHRASE": "backup_passphrase", "STORAGE": "storage", "GIT_HISTORY": "git_history",
    "SNAPSHOT_RETENTION_DAYS": "snapshot_retention_days", "SNAPSHOT_KEEP_MIN": "snapshot_keep_min",
    "SNAPSHOT_ON_CHANGE": "snapshot_on_change", "GITEA_REPO_URL": "gitea_url",
    "GITEA_USER": "gitea_user", "GITEA_TOKEN": "gitea_token", "GITEA_BRANCH": "gitea_branch",
    "GITEA_INSECURE": "gitea_insecure", "GIT_AUTHOR_NAME": "git_author_name",
    "GIT_AUTHOR_EMAIL": "git_author_email", "TELEGRAM_TOKEN": "telegram_token",
    "TELEGRAM_CHAT_ID": "telegram_chat", "WEB_RESTORE": "web_restore",
}


def _read_pem(path: str | None, base: Path) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute() and not p.exists():
        p = base / p
    return p.read_text(encoding="utf-8")


def import_legacy(db: Database, box: SecretBox, config_path: Path | None,
                  replace: bool = False) -> list[str]:
    report: list[str] = []

    settings = {key: os.environ[env] for env, key in ENV_MAP.items() if os.environ.get(env)}
    if os.environ.get("GITEA_CA_FILE"):
        settings["gitea_ca_pem"] = _read_pem(os.environ["GITEA_CA_FILE"], Path.cwd())
    if settings:
        changed = update_settings(db, box, settings)
        report.append(f"Настройки: обновлено {len(changed)} ({', '.join(changed) or 'без изменений'})")

    if not config_path:
        return report
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults") or {}
    existing = {r["name"]: r["id"] for r in db.query("SELECT id, name FROM devices")}
    for item in raw.get("devices") or []:
        merged = {**defaults, **item}
        name = str(merged.get("name", ""))
        pw_env = merged.pop("password_env", None)
        merged["password"] = os.environ.get(pw_env) if pw_env else os.environ.get("MT_PASSWORD")
        if merged.get("tls_ca"):
            merged["tls_ca"] = _read_pem(merged["tls_ca"], Path(config_path).parent)
        if name in existing and not replace:
            report.append(f"{name}: уже есть, пропущено (--replace — перезаписать)")
            continue
        try:
            save_device(db, box, merged, existing.get(name))
            report.append(f"{name}: {'обновлено' if name in existing else 'добавлено'}")
        except (ConfigError, OSError) as exc:
            report.append(f"{name}: ошибка — {exc}")
    return report
