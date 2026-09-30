"""Конфигурация: запуск — из окружения, всё остальное — из SQLite.

Окружение (только то, что нужно до открытия базы):
  DATA_DIR        база mtb.db, secret.key, known_hosts (по умолчанию ./data)
  BACKUP_DIR      папка бэкапов (по умолчанию ./backups)
  WEB_LISTEN      адрес веб-интерфейса (0.0.0.0:8080)
  WEB_TLS_CERT / WEB_TLS_KEY   HTTPS без обратного прокси
  WEB_COOKIE_SECURE            auto | true | false — флаг Secure у cookie сессии
  LOG_LEVEL

Устройства, расписание, хранение, Gitea, Telegram, пользователи — в веб-интерфейсе.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .db import Database
from .secretbox import SecretBox


class ConfigError(ValueError):
    """Ошибка в настройках — показывается пользователю как есть."""


NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _bool(v) -> bool:
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------- запуск

@dataclass
class Bootstrap:
    data_dir: Path
    backup_dir: Path
    web_listen: str
    web_tls_cert: str | None
    web_tls_key: str | None
    web_cookie_secure: bool

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mtb.db"


def load_bootstrap(data_dir: str | None = None) -> Bootstrap:
    cert = os.environ.get("WEB_TLS_CERT") or None
    secure = os.environ.get("WEB_COOKIE_SECURE", "auto").lower()
    return Bootstrap(
        data_dir=Path(data_dir or os.environ.get("DATA_DIR", "data")),
        backup_dir=Path(os.environ.get("BACKUP_DIR", "backups")),
        web_listen=os.environ.get("WEB_LISTEN", "0.0.0.0:8080"),
        web_tls_cert=cert,
        web_tls_key=os.environ.get("WEB_TLS_KEY") or None,
        web_cookie_secure=bool(cert) if secure == "auto" else _bool(secure),
    )


def open_storage(boot: Bootstrap) -> tuple[Database, SecretBox]:
    boot.data_dir.mkdir(parents=True, exist_ok=True)
    return Database(boot.db_path), SecretBox(boot.data_dir / "secret.key")


# ---------------------------------------------------------------- устройство

@dataclass
class Device:
    name: str
    host: str
    username: str
    password: str
    id: int | None = None
    enabled: bool = True
    notes: str = ""
    api_port: int = 8729
    ssh_port: int = 22
    timeout: float = 30
    encoding: str = "utf-8"
    tls_fingerprint: str | None = None   # SHA-256 сертификата api-ssl
    tls_ca: str | None = None            # PEM самого сертификата или CA
    tls_insecure: bool = False
    tls_legacy: bool = False
    certs: str | list[str] = "all"       # all | none | [имена]
    transport: str = "sftp"              # sftp | api | ssh
    config_only: bool = False
    api_binary: str = "base64"           # base64 | raw | skip
    api_b64_chunk: int = 12288
    cert_format: str | None = None       # p12 | pem

    def __post_init__(self) -> None:
        if not NAME_RE.match(self.name or ""):
            raise ConfigError("Имя: латиница, цифры, точка, дефис, подчёркивание (до 64 символов)")
        if not self.host:
            raise ConfigError(f"{self.name}: не указан адрес")
        if not self.username:
            raise ConfigError(f"{self.name}: не указан пользователь")
        if self.transport not in ("sftp", "api", "ssh"):
            raise ConfigError(f"{self.name}: transport должен быть sftp, api или ssh")
        if self.api_binary not in ("base64", "raw", "skip"):
            raise ConfigError(f"{self.name}: api_binary должен быть base64, raw или skip")
        if self.cert_format in ("", None):
            self.cert_format = "pem" if self.transport == "api" and self.api_binary == "skip" else "p12"
        if self.cert_format not in ("p12", "pem"):
            raise ConfigError(f"{self.name}: формат сертификатов — p12 или pem")
        if self.transport == "api" and self.api_binary == "skip" and self.cert_format == "p12":
            raise ConfigError(f"{self.name}: при api_binary=skip сертификаты можно выгружать только в pem")
        if not 3072 <= int(self.api_b64_chunk) <= 32768:
            raise ConfigError(f"{self.name}: размер куска base64 — от 3072 до 32768")
        for port in (self.api_port, self.ssh_port):
            if not 1 <= int(port) <= 65535:
                raise ConfigError(f"{self.name}: неверный порт {port}")
        if not 1 <= float(self.timeout) <= 600:
            raise ConfigError(f"{self.name}: таймаут — от 1 до 600 секунд")
        try:
            "".encode(self.encoding)
        except LookupError as exc:
            raise ConfigError(f"{self.name}: неизвестная кодировка {self.encoding}") from exc
        if self.tls_fingerprint:
            fp = self.tls_fingerprint.replace(":", "").replace(" ", "").lower()
            if not re.fullmatch(r"[0-9a-f]{64}", fp):
                raise ConfigError(f"{self.name}: отпечаток должен быть SHA-256 (64 hex-символа)")
        if self.tls_ca and "BEGIN CERTIFICATE" not in self.tls_ca:
            raise ConfigError(f"{self.name}: CA должен быть в формате PEM")
        if self.transport != "ssh" and not (self.tls_fingerprint or self.tls_ca or self.tls_insecure):
            raise ConfigError(f"{self.name}: для API-SSL укажите отпечаток, CA или отключите проверку")
        if isinstance(self.certs, list):
            self.certs = [str(c) for c in self.certs if str(c).strip()]
        elif self.certs not in ("all", "none"):
            raise ConfigError(f"{self.name}: сертификаты — all, none или список имён")

    @property
    def want_backup(self) -> bool:
        return not self.config_only and not (self.transport == "api" and self.api_binary == "skip")

    @property
    def want_certs(self) -> bool:
        return not self.config_only


DEVICE_FIELDS = ("name", "enabled", "notes", "host", "username", "api_port", "ssh_port", "timeout",
                 "encoding", "transport", "config_only", "api_binary", "api_b64_chunk", "cert_format",
                 "certs", "tls_fingerprint", "tls_ca", "tls_insecure", "tls_legacy")


def device_from_row(row, box: SecretBox) -> Device:
    return Device(
        id=row["id"], name=row["name"], enabled=bool(row["enabled"]), notes=row["notes"],
        host=row["host"], username=row["username"], password=box.decrypt(row["password_enc"]),
        api_port=row["api_port"], ssh_port=row["ssh_port"], timeout=row["timeout"],
        encoding=row["encoding"], transport=row["transport"], config_only=bool(row["config_only"]),
        api_binary=row["api_binary"], api_b64_chunk=row["api_b64_chunk"], cert_format=row["cert_format"],
        certs=json.loads(row["certs"]), tls_fingerprint=row["tls_fingerprint"] or None,
        tls_ca=row["tls_ca_pem"] or None, tls_insecure=bool(row["tls_insecure"]),
        tls_legacy=bool(row["tls_legacy"]),
    )


def device_public(dev: Device, db: Database | None = None) -> dict:
    """Для API: всё, кроме пароля."""
    d = {k: getattr(dev, k) for k in DEVICE_FIELDS}
    d["id"] = dev.id
    d["password_set"] = bool(dev.password)
    if db is not None and dev.id is not None:
        d["aliases"] = [r["name"] for r in db.query(
            "SELECT name FROM device_aliases WHERE device_id=? ORDER BY name", (dev.id,))]
    return d


def set_aliases(db: Database, device_id: int, names) -> list[str]:
    """Прежние имена устройства: бэкапы и журнал под ними показываются у этого устройства."""
    if isinstance(names, str):
        names = names.replace(",", "\n").splitlines()
    clean = sorted({str(n).strip() for n in names if str(n).strip()})
    me = db.one("SELECT name FROM devices WHERE id=?", (device_id,))
    for n in clean:
        if not NAME_RE.match(n):
            raise ConfigError(f"Прежнее имя {n}: латиница, цифры, . _ -")
        if me and n == me["name"]:
            raise ConfigError(f"{n} — текущее имя устройства")
        if db.one("SELECT 1 FROM devices WHERE name=?", (n,)):
            raise ConfigError(f"Устройство {n} существует — его имя нельзя сделать прежним именем другого")
        other = db.one("SELECT d.name FROM device_aliases a JOIN devices d ON d.id=a.device_id "
                       "WHERE a.name=? AND a.device_id<>?", (n, device_id))
        if other:
            raise ConfigError(f"{n} уже указано как прежнее имя устройства {other['name']}")
    now = time.time()
    with db.tx() as c:
        c.execute("DELETE FROM device_aliases WHERE device_id=?", (device_id,))
        for n in clean:
            c.execute("INSERT INTO device_aliases(name, device_id, created_at) VALUES(?,?,?)", (n, device_id, now))
    return clean


def save_device(db: Database, box: SecretBox, data: dict, device_id: int | None = None) -> Device:
    """Создать или обновить устройство. Пустой пароль при обновлении — оставить прежний."""
    current = None
    if device_id is not None:
        row = db.one("SELECT * FROM devices WHERE id=?", (device_id,))
        if row is None:
            raise KeyError("устройство не найдено")
        current = device_from_row(row, box)
    base = {k: getattr(current, k) for k in DEVICE_FIELDS} if current else {}
    merged = {**base, **{k: data[k] for k in DEVICE_FIELDS if k in data}}
    password = data.get("password") or (current.password if current else "")
    if not password:
        raise ConfigError("Укажите пароль пользователя на роутере")
    merged["name"] = str(merged.get("name", "")).strip()
    merged["host"] = str(merged.get("host", "")).strip()
    for k in ("tls_fingerprint", "tls_ca", "cert_format"):
        if not merged.get(k):
            merged[k] = None
    for k in ("enabled", "config_only", "tls_insecure", "tls_legacy"):
        merged[k] = _bool(merged.get(k, k == "enabled"))
    for k in ("api_port", "ssh_port", "api_b64_chunk"):
        if k in merged and merged[k] is not None:
            try:
                merged[k] = int(merged[k])
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"{k}: ожидалось целое число") from exc
    if "timeout" in merged:
        merged["timeout"] = float(merged["timeout"])
    dev = Device(password=password, **merged)       # проверка
    now = time.time()
    cols = dict(name=dev.name, enabled=int(dev.enabled), notes=dev.notes or "", host=dev.host,
                username=dev.username, password_enc=box.encrypt(dev.password), api_port=dev.api_port,
                ssh_port=dev.ssh_port, timeout=dev.timeout, encoding=dev.encoding, transport=dev.transport,
                config_only=int(dev.config_only), api_binary=dev.api_binary, api_b64_chunk=dev.api_b64_chunk,
                cert_format=dev.cert_format, certs=json.dumps(dev.certs), tls_fingerprint=dev.tls_fingerprint,
                tls_ca_pem=dev.tls_ca, tls_insecure=int(dev.tls_insecure), tls_legacy=int(dev.tls_legacy),
                updated_at=now)
    alias_owner = db.one("SELECT device_id FROM device_aliases WHERE name=?", (dev.name,))
    if alias_owner and alias_owner["device_id"] != device_id:
        owner = db.one("SELECT name FROM devices WHERE id=?", (alias_owner["device_id"],))
        raise ConfigError(f"Имя {dev.name} раньше было у устройства {owner['name'] if owner else '?'}: "
                          f"его бэкапы хранятся под этим именем")
    try:
        with db.tx() as c:
            if current is not None and current.name != dev.name:
                c.execute("INSERT OR REPLACE INTO device_aliases(name, device_id, created_at) VALUES(?,?,?)",
                          (current.name, device_id, now))
                c.execute("DELETE FROM device_aliases WHERE name=? AND device_id=?", (dev.name, device_id))
            if device_id is None:
                cols["created_at"] = now
                cur = c.execute(f"INSERT INTO devices({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                                tuple(cols.values()))
                dev.id = cur.lastrowid
            else:
                c.execute(f"UPDATE devices SET {','.join(f'{k}=?' for k in cols)} WHERE id=?",
                          (*cols.values(), device_id))
                dev.id = device_id
    except Exception as exc:
        if "UNIQUE" in str(exc):
            raise ConfigError(f"Устройство с именем {dev.name} уже есть") from exc
        raise
    return dev


def load_devices(db: Database, box: SecretBox, only_enabled: bool = False) -> list[Device]:
    sql = "SELECT * FROM devices" + (" WHERE enabled=1" if only_enabled else "") + " ORDER BY name"
    return [device_from_row(r, box) for r in db.query(sql)]


# ---------------------------------------------------------------- настройки

# ключ: (тип, значение по умолчанию, секрет)
SETTINGS_SPEC: dict[str, tuple[type, object, bool]] = {
    "schedule": (str, "0 3 * * *", False),
    "timezone": (str, "Europe/Moscow", False),
    "workers": (int, 4, False),
    "backup_passphrase": (str, "", True),
    "storage": (str, "git", False),
    "git_history": (bool, True, False),
    "snapshot_retention_days": (int, 30, False),
    "snapshot_keep_min": (int, 7, False),
    "snapshot_on_change": (bool, False, False),
    "gitea_url": (str, "", False),
    "gitea_user": (str, "", False),
    "gitea_token": (str, "", True),
    "gitea_branch": (str, "main", False),
    "gitea_ca_pem": (str, "", False),
    "gitea_insecure": (bool, False, False),
    "git_author_name": (str, "mtb", False),
    "git_author_email": (str, "mtb@localhost", False),
    "telegram_token": (str, "", True),
    "telegram_chat": (str, "", False),
    "web_restore": (bool, False, False),
    "notify_lang": (str, "en", False),
    "update_check": (bool, True, False),
    "update_channel": (str, "auto", False),
}


def read_settings(db: Database, box: SecretBox) -> dict:
    raw = db.get_settings()
    out = {}
    for key, (typ, default, secret) in SETTINGS_SPEC.items():
        value = raw.get(key, default)
        if secret:
            value = box.decrypt(value) if value else ""
        out[key] = typ(value) if typ is not bool else _bool(value)
    return out


def settings_public(values: dict) -> dict:
    return {k: ({"set": bool(values[k])} if SETTINGS_SPEC[k][2] else values[k]) for k in SETTINGS_SPEC}


def update_settings(db: Database, box: SecretBox, changes: dict) -> list[str]:
    """Проверяет и сохраняет изменения. Секрет: пустое значение — не менять, None — удалить."""
    current = read_settings(db, box)
    new = dict(current)
    for key, value in changes.items():
        if key not in SETTINGS_SPEC:
            raise ConfigError(f"Неизвестная настройка: {key}")
        typ, _, secret = SETTINGS_SPEC[key]
        if secret:
            if value is None:
                new[key] = ""
            elif value != "":
                new[key] = str(value)
            continue
        try:
            new[key] = _bool(value) if typ is bool else typ(value)
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{key}: неверное значение") from exc
    validate_settings(new)
    changed = [k for k in SETTINGS_SPEC if new[k] != current[k]]
    db.set_settings({k: (box.encrypt(new[k]) if SETTINGS_SPEC[k][2] else new[k]) for k in changed})
    return changed


def validate_settings(v: dict) -> None:
    from apscheduler.triggers.cron import CronTrigger
    try:
        tz = ZoneInfo(v["timezone"])
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"Неизвестный часовой пояс: {v['timezone']}") from exc
    try:
        CronTrigger.from_crontab(v["schedule"], timezone=tz)
    except ValueError as exc:
        raise ConfigError(f"Расписание: {exc}") from exc
    if not 1 <= v["workers"] <= 32:
        raise ConfigError("Параллельных устройств — от 1 до 32")
    if v["storage"] not in ("git", "snapshots"):
        raise ConfigError("Хранение — git или snapshots")
    if v["snapshot_retention_days"] < 0 or v["snapshot_keep_min"] < 1:
        raise ConfigError("Срок хранения ≥ 0 дней, минимум снимков ≥ 1")
    if v["gitea_url"]:
        if v["storage"] != "git":
            raise ConfigError("Push в Gitea работает только с хранением git")
        if not v["gitea_url"].startswith(("https://", "http://")):
            raise ConfigError("URL репозитория Gitea должен начинаться с https://")
        if not (v["gitea_user"] and v["gitea_token"]):
            raise ConfigError("Для Gitea нужны пользователь и токен")
    if v["gitea_ca_pem"] and "BEGIN CERTIFICATE" not in v["gitea_ca_pem"]:
        raise ConfigError("CA Gitea должен быть в формате PEM")
    if v["update_channel"] not in ("auto", "stable", "prerelease"):
        raise ConfigError("Канал обновлений — auto, stable или prerelease")
    if v["notify_lang"] not in ("ru", "en"):
        raise ConfigError("Язык уведомлений — ru или en")
    if bool(v["telegram_token"]) != bool(v["telegram_chat"]):
        raise ConfigError("Для Telegram нужны и токен бота, и chat_id")


# ---------------------------------------------------------------- рабочий объект

@dataclass
class Settings:
    devices: list[Device]
    backup_passphrase: str
    data_dir: Path
    backup_dir: Path
    storage: str
    snapshot_retention_days: int
    snapshot_keep_min: int
    snapshot_on_change: bool
    git_history: bool
    schedule: str
    timezone: str
    workers: int
    git_url: str | None
    git_user: str | None
    git_token: str | None
    git_branch: str
    git_author_name: str
    git_author_email: str
    git_ca: str | None
    git_insecure: bool
    tg_token: str | None
    tg_chat: str | None
    web_restore: bool = False
    notify_lang: str = "ru"
    web_listen: str = "0.0.0.0:8080"
    web_tls_cert: str | None = None
    web_tls_key: str | None = None
    web_cookie_secure: bool = False
    aliases: dict = field(default_factory=dict)     # прежнее имя устройства -> текущее
    extra: dict = field(default_factory=dict)


def load(boot: Bootstrap, db: Database, box: SecretBox) -> Settings:
    """Собирает актуальные настройки из базы. Вызывается перед каждым прогоном."""
    v = read_settings(db, box)
    git_ca = None
    if v["gitea_ca_pem"]:
        path = boot.data_dir / "gitea-ca.pem"
        if not path.exists() or path.read_text() != v["gitea_ca_pem"]:
            path.write_text(v["gitea_ca_pem"])
        git_ca = str(path)
    return Settings(
        devices=load_devices(db, box),
        backup_passphrase=v["backup_passphrase"],
        data_dir=boot.data_dir, backup_dir=boot.backup_dir,
        storage=v["storage"], snapshot_retention_days=v["snapshot_retention_days"],
        snapshot_keep_min=v["snapshot_keep_min"], snapshot_on_change=v["snapshot_on_change"],
        git_history=v["git_history"], schedule=v["schedule"], timezone=v["timezone"],
        workers=v["workers"], git_url=v["gitea_url"] or None, git_user=v["gitea_user"] or None,
        git_token=v["gitea_token"] or None, git_branch=v["gitea_branch"] or "main",
        git_author_name=v["git_author_name"], git_author_email=v["git_author_email"],
        git_ca=git_ca, git_insecure=v["gitea_insecure"],
        tg_token=v["telegram_token"] or None, tg_chat=v["telegram_chat"] or None,
        web_restore=v["web_restore"], notify_lang=v["notify_lang"], web_listen=boot.web_listen,
        web_tls_cert=boot.web_tls_cert, web_tls_key=boot.web_tls_key,
        web_cookie_secure=boot.web_cookie_secure,
        aliases=load_aliases(db),
    )


def load_aliases(db: Database) -> dict:
    return {r["name"]: r["current"] for r in db.query(
        "SELECT a.name, d.name AS current FROM device_aliases a JOIN devices d ON d.id = a.device_id")}
