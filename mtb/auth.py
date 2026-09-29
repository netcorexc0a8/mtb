"""Пользователи, пароли (scrypt), сессии, защита от перебора.

Первый запуск: создаётся пользователь admin без пароля. При первом входе он
придумывает пароль (с подтверждением). Так же работает сброс пароля из
консоли: `mtb reset-password admin`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import threading
import time

from .config import ConfigError
from .db import Database

log = logging.getLogger("mtb.auth")

SESSION_TTL = 12 * 3600
SESSION_REFRESH = 3600
MIN_PASSWORD = 10
ROLES = ("admin", "viewer")
SCRYPT = dict(n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **SCRYPT)
    return "scrypt${n}${r}${p}${s}${d}".format(
        n=SCRYPT["n"], r=SCRYPT["r"], p=SCRYPT["p"],
        s=base64.b64encode(salt).decode(), d=base64.b64encode(digest).decode())


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, n, r, p, s, d = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(s), dklen=32,
                                n=int(n), r=int(r), p=int(p), maxmem=SCRYPT["maxmem"])
        return hmac.compare_digest(digest, base64.b64decode(d))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password(secrets.token_hex(8))   # чтобы время ответа не выдавало логины


def check_new_password(username: str, password: str, confirm: str) -> None:
    if password != confirm:
        raise ConfigError("Пароли не совпадают")
    if len(password) < MIN_PASSWORD:
        raise ConfigError(f"Пароль должен быть не короче {MIN_PASSWORD} символов")
    if password.lower() == username.lower():
        raise ConfigError("Пароль не должен совпадать с логином")
    if len(set(password)) < 4:
        raise ConfigError("Пароль слишком простой")


def ensure_admin(db: Database) -> bool:
    """Создаёт admin без пароля, если пользователей ещё нет. True — если создан."""
    if db.one("SELECT 1 FROM users LIMIT 1"):
        return False
    with db.tx() as c:
        c.execute("INSERT INTO users(username, password_hash, role, must_set_password, created_at) "
                  "VALUES('admin', NULL, 'admin', 1, ?)", (time.time(),))
    log.warning("Создан пользователь admin. Откройте веб-интерфейс и задайте пароль при первом входе.")
    return True


def reset_password(db: Database, username: str) -> bool:
    row = db.one("SELECT id FROM users WHERE username=?", (username,))
    if row is None:
        return False
    with db.tx() as c:
        c.execute("UPDATE users SET password_hash=NULL, must_set_password=1 WHERE id=?", (row["id"],))
        c.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
    return True


def set_password(db: Database, user_id: int, password: str, must_change: bool = False) -> None:
    with db.tx() as c:
        c.execute("UPDATE users SET password_hash=?, must_set_password=? WHERE id=?",
                  (hash_password(password), int(must_change), user_id))


def authenticate(db: Database, username: str, password: str):
    """Строка пользователя или None. Время ответа не зависит от существования логина."""
    row = db.one("SELECT * FROM users WHERE username=?", (username,))
    ok = verify_password(password, row["password_hash"] if row and row["password_hash"] else _DUMMY_HASH)
    return row if ok and row else None


# ---------------------------------------------------------------- сессии

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Database, user_id: int, ip: str) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with db.tx() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        c.execute("INSERT INTO sessions(token_hash, user_id, created_at, expires_at, ip) VALUES(?,?,?,?,?)",
                  (_token_hash(token), user_id, now, now + SESSION_TTL, ip))
        c.execute("UPDATE users SET last_login=? WHERE id=?", (now, user_id))
    return token


def session_user(db: Database, token: str | None):
    if not token:
        return None
    now = time.time()
    row = db.one("SELECT u.*, s.expires_at AS s_expires, s.token_hash AS s_hash FROM sessions s "
                 "JOIN users u ON u.id = s.user_id WHERE s.token_hash=? AND s.expires_at > ?",
                 (_token_hash(token), now))
    if row and row["s_expires"] - now < SESSION_TTL - SESSION_REFRESH:
        with db.tx() as c:           # скользящее продление, не чаще раза в час
            c.execute("UPDATE sessions SET expires_at=? WHERE token_hash=?", (now + SESSION_TTL, row["s_hash"]))
    return row


def delete_session(db: Database, token: str | None) -> None:
    if token:
        with db.tx() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


# ---------------------------------------------------------------- перебор

class Throttle:
    """Не больше 10 неудачных попыток за 15 минут с одного адреса."""

    def __init__(self, limit: int = 10, window: float = 900):
        self.limit, self.window = limit, window
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def blocked(self, ip: str) -> bool:
        now = time.time()
        with self._lock:
            fails = [t for t in self._fails.get(ip, []) if now - t < self.window]
            self._fails[ip] = fails
            return len(fails) >= self.limit

    def fail(self, ip: str) -> None:
        with self._lock:
            self._fails.setdefault(ip, []).append(time.time())

    def reset(self, ip: str) -> None:
        with self._lock:
            self._fails.pop(ip, None)
