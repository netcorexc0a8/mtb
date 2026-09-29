"""SQLite: настройки, устройства, пользователи, сессии, журнал запусков, аудит.

Сами бэкапы остаются файлами в BACKUP_DIR (снимки или git) — их удобно
восстанавливать без приложения, отправлять в Gitea, а бинарные .backup
не раздувают базу.

Секреты (пароли устройств, BACKUP_PASSPHRASE, токены) хранятся
зашифрованными ключом из DATA_DIR/secret.key — см. secretbox.py.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = [
    # v1
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE devices (
        id              INTEGER PRIMARY KEY,
        name            TEXT NOT NULL UNIQUE,
        enabled         INTEGER NOT NULL DEFAULT 1,
        host            TEXT NOT NULL,
        username        TEXT NOT NULL,
        password_enc    TEXT NOT NULL DEFAULT '',
        api_port        INTEGER NOT NULL DEFAULT 8729,
        ssh_port        INTEGER NOT NULL DEFAULT 22,
        timeout         REAL    NOT NULL DEFAULT 30,
        encoding        TEXT    NOT NULL DEFAULT 'utf-8',
        transport       TEXT    NOT NULL DEFAULT 'sftp',
        config_only     INTEGER NOT NULL DEFAULT 0,
        api_binary      TEXT    NOT NULL DEFAULT 'base64',
        api_b64_chunk   INTEGER NOT NULL DEFAULT 12288,
        cert_format     TEXT,
        certs           TEXT    NOT NULL DEFAULT '"all"',
        tls_fingerprint TEXT,
        tls_ca_pem      TEXT,
        tls_insecure    INTEGER NOT NULL DEFAULT 0,
        tls_legacy      INTEGER NOT NULL DEFAULT 0,
        notes           TEXT    NOT NULL DEFAULT '',
        created_at      REAL    NOT NULL,
        updated_at      REAL    NOT NULL
    );
    CREATE TABLE users (
        id                INTEGER PRIMARY KEY,
        username          TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash     TEXT,
        role              TEXT NOT NULL DEFAULT 'viewer',
        must_set_password INTEGER NOT NULL DEFAULT 1,
        created_at        REAL NOT NULL,
        last_login        REAL
    );
    CREATE TABLE sessions (
        token_hash TEXT PRIMARY KEY,
        user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        ip         TEXT
    );
    CREATE TABLE runs (
        id          INTEGER PRIMARY KEY,
        started_at  REAL NOT NULL,
        finished_at REAL,
        kind        TEXT NOT NULL,
        user        TEXT,
        devices     TEXT NOT NULL,
        ok          TEXT NOT NULL DEFAULT '[]',
        failed      TEXT NOT NULL DEFAULT '{}',
        changed     TEXT NOT NULL DEFAULT '{}',
        warnings    TEXT NOT NULL DEFAULT '[]'
    );
    CREATE TABLE audit (
        id      INTEGER PRIMARY KEY,
        ts      REAL NOT NULL,
        user    TEXT,
        action  TEXT NOT NULL,
        details TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX runs_started ON runs(started_at);
    CREATE INDEX audit_ts ON audit(ts);
    """,
]


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._migrate()
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
        return conn

    def _migrate(self) -> None:
        conn = self._conn()
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for i, script in enumerate(SCHEMA[version:], start=version + 1):
            conn.executescript("BEGIN;" + script + f"PRAGMA user_version={i};COMMIT;")

    @contextmanager
    def tx(self):
        """Транзакция на запись (одна за раз — SQLite так и так пишет последовательно)."""
        with self._write_lock:
            conn = self._conn()
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise

    def query(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        return self._conn().execute(sql, args).fetchall()

    def one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        return self._conn().execute(sql, args).fetchone()

    # ---------------------------------------------------------------- настройки

    def get_settings(self) -> dict:
        return {r["key"]: json.loads(r["value"]) for r in self.query("SELECT key, value FROM settings")}

    def set_settings(self, values: dict) -> None:
        with self.tx() as c:
            for k, v in values.items():
                c.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                          "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, json.dumps(v)))

    # ---------------------------------------------------------------- журнал

    def audit(self, user: str | None, action: str, details: str = "") -> None:
        with self.tx() as c:
            c.execute("INSERT INTO audit(ts, user, action, details) VALUES(?,?,?,?)",
                      (time.time(), user, action, details[:2000]))
