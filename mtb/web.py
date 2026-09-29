"""Веб-интерфейс: бэкапы, устройства, настройки, пользователи, журнал.

Стандартная библиотека, без фреймворков и CDN. Статика — mtb/web/.

Безопасность:
  - вход по логину и паролю (scrypt), сессия в cookie HttpOnly + SameSite=Strict;
  - первый запуск: admin без пароля, пароль задаётся при первом входе;
  - изменяющие запросы требуют X-Requested-With: mtb (защита от CSRF);
  - роли: admin — всё, viewer — просмотр и скачивание бэкапов;
  - пароли устройств и токены не отдаются в API, только признак «задан»;
  - строгий CSP, защита от перебора (10 попыток за 15 минут с адреса).
"""
from __future__ import annotations

import json
import logging
import mimetypes
import re
import ssl
import threading
import time
from datetime import date, datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from . import __version__, auth, config
from .catalog import MAX_CONTENT, Catalog
from .config import ConfigError
from .mikrotik import FAILURE_RE, check_device, fetch_fingerprint, restore_config
from .notify import telegram_send
from .probe import format_report, probe_device
from .runner import RUN_LOCK, run_once

log = logging.getLogger("mtb.web")

STATIC_DIR = Path(__file__).with_name("web")
STATIC = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css", "/favicon.svg": "favicon.svg"}
COOKIE = "mtbk_session"
BULK_LIMIT = 200
MAX_BODY = 1024 * 1024

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; "
                               "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
                               "base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}

ROUTES: list[tuple[str, re.Pattern, str, str | None]] = []   # (метод, путь, обработчик, роль)


def route(method: str, pattern: str, role: str | None = "viewer"):
    """role: None — без входа, viewer — любой вошедший, admin — только администратор."""
    def deco(fn):
        ROUTES.append((method, re.compile(f"^{pattern}$"), fn.__name__, role))
        return fn
    return deco


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Request:
    def __init__(self, handler: "_Handler", params: tuple, query: dict, user):
        self.h, self.params, self.query, self.user = handler, params, query, user
        self._body = None

    @property
    def body(self) -> dict:
        if self._body is None:
            self._body = self.h.read_json()
        return self._body

    @property
    def username(self) -> str | None:
        return self.user["username"] if self.user else None

    @property
    def ip(self) -> str:
        return self.h.client_address[0]


class WebApp:
    def __init__(self, boot: config.Bootstrap, db, box, on_settings_changed=None):
        self.boot, self.db, self.box = boot, db, box
        self.on_settings_changed = on_settings_changed
        self.throttle = auth.Throttle()
        host, _, port = boot.web_listen.rpartition(":")
        self.address = (host.strip("[]") or "0.0.0.0", int(port or 8080))
        auth.ensure_admin(db)

    def settings(self) -> config.Settings:
        return config.load(self.boot, self.db, self.box)

    def audit(self, req: Request, action: str, details: str = "") -> None:
        self.db.audit(req.username, action, details)

    # ================================================================ вход

    @route("GET", "/api/auth/state", role=None)
    def auth_state(self, req: Request):
        if req.user:
            return {"authenticated": True, "user": req.user["username"]}
        first = self.db.one("SELECT username FROM users WHERE password_hash IS NULL AND role='admin' "
                            "AND (SELECT COUNT(*) FROM users WHERE password_hash IS NOT NULL) = 0")
        return {"authenticated": False, "first_run": bool(first),
                "first_user": first["username"] if first else None}

    @route("POST", "/api/auth/login", role=None)
    def login(self, req: Request):
        if self.throttle.blocked(req.ip):
            raise ApiError(429, "Слишком много попыток. Подождите 15 минут.")
        username = str(req.body.get("username", "")).strip()
        password = str(req.body.get("password", ""))
        row = self.db.one("SELECT * FROM users WHERE username=?", (username,))
        if row is not None and row["password_hash"] is None:
            return {"setup": True, "username": row["username"], "need_current": False}
        user = auth.authenticate(self.db, username, password)
        if user is None:
            self.throttle.fail(req.ip)
            self.db.audit(username or "?", "login_failed", req.ip)
            time.sleep(0.5)
            raise ApiError(401, "Неверный логин или пароль")
        self.throttle.reset(req.ip)
        if user["must_set_password"]:
            return {"setup": True, "username": user["username"], "need_current": True}
        req.h.new_session = auth.create_session(self.db, user["id"], req.ip)
        self.db.audit(user["username"], "login", req.ip)
        return {"ok": True}

    @route("POST", "/api/auth/setup", role=None)
    def setup_password(self, req: Request):
        """Первый вход или временный пароль: задать свой пароль с подтверждением."""
        if self.throttle.blocked(req.ip):
            raise ApiError(429, "Слишком много попыток. Подождите 15 минут.")
        b = req.body
        username = str(b.get("username", "")).strip()
        row = self.db.one("SELECT * FROM users WHERE username=?", (username,))
        if row is None or not row["must_set_password"]:
            self.throttle.fail(req.ip)
            raise ApiError(400, "Для этого пользователя смена пароля при входе не требуется")
        if row["password_hash"] is not None and not auth.verify_password(str(b.get("current", "")),
                                                                         row["password_hash"]):
            self.throttle.fail(req.ip)
            raise ApiError(401, "Неверный текущий (временный) пароль")
        password = str(b.get("password", ""))
        auth.check_new_password(row["username"], password, str(b.get("confirm", "")))
        auth.set_password(self.db, row["id"], password)
        self.throttle.reset(req.ip)
        req.h.new_session = auth.create_session(self.db, row["id"], req.ip)
        self.db.audit(row["username"], "password_set", "первый вход" if row["password_hash"] is None else "временный пароль")
        return {"ok": True}

    @route("POST", "/api/auth/logout", role=None)
    def logout(self, req: Request):
        auth.delete_session(self.db, req.h.cookie_token())
        req.h.clear_session = True
        return {"ok": True}

    @route("GET", "/healthz", role=None)
    def healthz(self, req: Request):
        row = self.db.one("SELECT MAX(finished_at) AS t FROM runs WHERE kind='scheduled' AND failed='{}'")
        return {"ok": True, "last_success": row["t"] if row else None}

    @route("GET", "/api/me")
    def me(self, req: Request):
        s = self.settings()
        cat = Catalog(s)
        return {"user": req.username, "role": req.user["role"], "can_write": req.user["role"] == "admin",
                "version": __version__, "timezone": s.timezone, "mode": cat.mode, "restore": s.web_restore,
                "devices": cat.devices(), "configured": [d.name for d in s.devices],
                "passphrase_set": bool(s.backup_passphrase)}

    @route("POST", "/api/me/password")
    def change_own_password(self, req: Request):
        b = req.body
        if not auth.verify_password(str(b.get("current", "")), req.user["password_hash"]):
            raise ApiError(400, "Неверный текущий пароль")
        auth.check_new_password(req.username, str(b.get("password", "")), str(b.get("confirm", "")))
        auth.set_password(self.db, req.user["id"], str(b["password"]))
        with self.db.tx() as c:          # остальные сессии пользователя — закрыть
            c.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?",
                      (req.user["id"], req.user["s_hash"]))
        self.audit(req, "password_changed")
        return {"ok": True}

    # ================================================================ бэкапы

    @route("GET", "/api/backups")
    def backups_list(self, req: Request):
        q = req.query
        cat = Catalog(self.settings())
        device, kind = q.get("device", ""), q.get("type", "")
        search = q.get("search", "").lower().strip()
        d_from = date.fromisoformat(q["from"]) if q.get("from") else None
        d_to = date.fromisoformat(q["to"]) if q.get("to") else None
        out = []
        for e in cat.list():
            day = e.created.date()
            if device and e.device != device or kind and e.type != kind:
                continue
            if d_from and day < d_from or d_to and day > d_to:
                continue
            if search and search not in f"{e.device} {e.filename} {e.notes}".lower():
                continue
            out.append(e.public())
        return out

    @route("GET", "/api/backups/types")
    def backups_types(self, req: Request):
        counts: dict[str, int] = {}
        for e in Catalog(self.settings()).list():
            counts[e.type] = counts.get(e.type, 0) + 1
        return [{"type": k, "count": v} for k, v in sorted(counts.items())]

    @route("POST", "/api/backups", role="admin")
    def backup_create(self, req: Request):
        return self._backup_now(req, str(req.body.get("device", "")), str(req.body.get("notes", ""))[:500])

    def _backup_now(self, req: Request, device: str, notes: str):
        s = self.settings()
        if device not in {d.name for d in s.devices}:
            raise ApiError(400, "Неизвестное устройство")
        res = run_once(s, only=[device], kind="manual", notes=notes, db=self.db, user=req.username)
        self.audit(req, "backup_manual", f"{device}: {'ok' if res.success else 'ошибка'}")
        if not res.success:
            raise ApiError(502, res.failed.get(device) or "; ".join(res.failed.values()))
        return {"ok": True, "changed": res.changed.get(device, []), "warnings": res.warnings}

    @route("POST", "/api/backups/bulk-delete/preview", role="admin")
    def bulk_preview(self, req: Request):
        ids = list(req.body.get("ids", []))
        cat = Catalog(self.settings())
        per: dict[str, dict] = {}
        for token in ids[:BULK_LIMIT]:
            e = cat.get(token)
            row = per.setdefault(e.device, {"device": e.device, "deletable": 0, "protected": 0})
            row["deletable" if e.deletable else "protected"] += 1
        rows = sorted(per.values(), key=lambda r: r["device"])
        return {"devices": rows, "total": sum(r["deletable"] for r in rows),
                "protected": sum(r["protected"] for r in rows), "limit": BULK_LIMIT,
                "over_limit": len(ids) > BULK_LIMIT}

    @route("POST", "/api/backups/bulk-delete", role="admin")
    def bulk_delete(self, req: Request):
        ids = list(req.body.get("ids", []))
        if len(ids) > BULK_LIMIT:
            raise ApiError(400, f"Не больше {BULK_LIMIT} за раз")
        cat = Catalog(self.settings())
        deleted, failures = 0, []
        with RUN_LOCK:
            for token in ids:
                try:
                    cat.delete(cat.get(token))
                    deleted += 1
                except Exception as exc:  # noqa: BLE001
                    failures.append({"id": token, "error": str(exc)})
        self.audit(req, "backup_bulk_delete", f"удалено {deleted}, ошибок {len(failures)}")
        return {"deleted": deleted, "failures": failures}

    @route("GET", "/api/backups/(?P<id>[A-Za-z0-9_-]+)/content")
    def backup_content(self, req: Request, id):
        cat = Catalog(self.settings())
        e = cat.get(id)
        data = cat.read(e)
        return {**e.public(), "content": cat.decode(e.device, data[:MAX_CONTENT]),
                "truncated": len(data) > MAX_CONTENT, "files": cat.files(e)}

    @route("GET", "/api/backups/(?P<a>[A-Za-z0-9_-]+)/diff/(?P<b>[A-Za-z0-9_-]+)")
    def backup_diff(self, req: Request, a, b):
        cat = Catalog(self.settings())
        ea, eb = cat.get(a), cat.get(b)
        if ea.created > eb.created:
            ea, eb = eb, ea
        side = lambda e: {**e.public(), "text": cat.decode(e.device, cat.read(e)[:MAX_CONTENT])}  # noqa: E731
        return {"from": side(ea), "to": side(eb)}

    @route("GET", "/api/backups/(?P<id>[A-Za-z0-9_-]+)/download")
    def backup_download(self, req: Request, id):
        cat = Catalog(self.settings())
        e = cat.get(id)
        rel = req.query.get("file", "config.rsc")
        data = cat.read(e, rel)
        fname = e.filename if rel == "config.rsc" else \
            f"{e.device}_{e.created:%Y-%m-%d_%H%M%S}_{rel.replace('/', '_')}"
        self.db.audit(req.username, "backup_download", f"{e.device}: {rel}")
        req.h.send_bytes(data, fname)

    @route("POST", "/api/backups/(?P<id>[A-Za-z0-9_-]+)/restore", role="admin")
    def backup_restore(self, req: Request, id):
        s = self.settings()
        if not s.web_restore:
            raise ApiError(403, "Восстановление выключено (Настройки → Веб-интерфейс)")
        cat = Catalog(s)
        e = cat.get(id)
        dev = next((d for d in s.devices if d.name == e.device), None)
        if dev is None:
            raise ApiError(400, "Устройства нет в списке устройств")
        with RUN_LOCK:
            output = restore_config(dev, s.data_dir / "known_hosts", cat.read(e))
        ok = not FAILURE_RE.search(output)
        self.audit(req, "backup_restore", f"{e.device} из {e.filename}: {'ok' if ok else 'с ошибками'}")
        return {"ok": ok, "output": output[-20000:]}

    @route("DELETE", "/api/backups/(?P<id>[A-Za-z0-9_-]+)", role="admin")
    def backup_delete(self, req: Request, id):
        cat = Catalog(self.settings())
        e = cat.get(id)
        with RUN_LOCK:
            cat.delete(e)
        self.audit(req, "backup_delete", f"{e.device}: {e.filename}")
        return {"ok": True}

    # ================================================================ устройства

    @route("GET", "/api/devices")
    def devices_list(self, req: Request):
        last = self._last_results()
        return [{**config.device_public(d), "last": last.get(d.name)}
                for d in config.load_devices(self.db, self.box)]

    def _last_results(self) -> dict:
        """Последний результат по каждому устройству из журнала запусков."""
        out: dict[str, dict] = {}
        for r in self.db.query("SELECT * FROM runs WHERE finished_at IS NOT NULL "
                               "ORDER BY started_at DESC LIMIT 200"):
            failed, ok = json.loads(r["failed"]), json.loads(r["ok"])
            for name in json.loads(r["devices"]):
                if name in out:
                    continue
                if name in failed:
                    out[name] = {"ok": False, "at": r["started_at"], "error": failed[name]}
                elif name in ok:
                    out[name] = {"ok": True, "at": r["started_at"]}
        return out

    @route("POST", "/api/devices", role="admin")
    def device_create(self, req: Request):
        dev = config.save_device(self.db, self.box, req.body)
        self.audit(req, "device_create", dev.name)
        return config.device_public(dev)

    @route("GET", "/api/devices/(?P<id>\\d+)")
    def device_get(self, req: Request, id):
        row = self.db.one("SELECT * FROM devices WHERE id=?", (int(id),))
        if row is None:
            raise KeyError("устройство не найдено")
        return config.device_public(config.device_from_row(row, self.box))

    @route("PUT", "/api/devices/(?P<id>\\d+)", role="admin")
    def device_update(self, req: Request, id):
        dev = config.save_device(self.db, self.box, req.body, int(id))
        changed = sorted(k for k in req.body if k != "password") + (["password"] if req.body.get("password") else [])
        self.audit(req, "device_update", f"{dev.name}: {', '.join(changed)}")
        return config.device_public(dev)

    @route("DELETE", "/api/devices/(?P<id>\\d+)", role="admin")
    def device_delete(self, req: Request, id):
        row = self.db.one("SELECT name FROM devices WHERE id=?", (int(id),))
        if row is None:
            raise KeyError("устройство не найдено")
        with self.db.tx() as c:
            c.execute("DELETE FROM devices WHERE id=?", (int(id),))
        self.audit(req, "device_delete", row["name"])
        return {"ok": True}

    def _device(self, id) -> tuple[config.Device, config.Settings]:
        s = self.settings()
        dev = next((d for d in s.devices if d.id == int(id)), None)
        if dev is None:
            raise KeyError("устройство не найдено")
        return dev, s

    @route("POST", "/api/devices/(?P<id>\\d+)/check", role="admin")
    def device_check(self, req: Request, id):
        dev, s = self._device(id)
        try:
            info = check_device(dev, s.data_dir / "known_hosts")
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": not info["missing_policies"], **info}

    @route("POST", "/api/devices/(?P<id>\\d+)/probe", role="admin")
    def device_probe(self, req: Request, id):
        dev, s = self._device(id)
        with RUN_LOCK:
            rep = probe_device(dev, s.data_dir / "known_hosts", use_sftp=bool(req.body.get("sftp", True)))
        return {"ok": not rep.error, "report": format_report(rep), "recommendation": rep.recommendation}

    @route("POST", "/api/devices/(?P<id>\\d+)/backup", role="admin")
    def device_backup(self, req: Request, id):
        dev, _ = self._device(id)
        return self._backup_now(req, dev.name, str(req.body.get("notes", ""))[:500])

    @route("POST", "/api/tools/fingerprint", role="admin")
    def tool_fingerprint(self, req: Request):
        host = str(req.body.get("host", "")).strip()
        port = int(req.body.get("port") or 8729)
        if not host:
            raise ApiError(400, "Укажите адрес")
        try:
            info = fetch_fingerprint(host, port)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(502, f"{type(exc).__name__}: {exc}") from exc
        return info

    # ================================================================ настройки

    def _settings_payload(self) -> dict:
        from apscheduler.triggers.cron import CronTrigger
        from zoneinfo import ZoneInfo
        v = config.read_settings(self.db, self.box)
        tz = ZoneInfo(v["timezone"])
        nxt = CronTrigger.from_crontab(v["schedule"], timezone=tz).get_next_fire_time(None, datetime.now(tz))
        return {"settings": config.settings_public(v), "next_run": nxt.isoformat() if nxt else None,
                "cookie_secure": self.boot.web_cookie_secure}

    @route("GET", "/api/settings", role="admin")
    def settings_get(self, req: Request):
        return self._settings_payload()

    @route("PUT", "/api/settings", role="admin")
    def settings_put(self, req: Request):
        changed = config.update_settings(self.db, self.box, dict(req.body))
        if changed:
            self.audit(req, "settings_update", ", ".join(changed))
            if self.on_settings_changed:
                self.on_settings_changed()
        return {"ok": True, "changed": changed, **self._settings_payload()}

    @route("POST", "/api/settings/test-telegram", role="admin")
    def settings_test_telegram(self, req: Request):
        s = self.settings()
        if not (s.tg_token and s.tg_chat):
            raise ApiError(400, "Сначала сохраните токен бота и chat_id")
        try:
            telegram_send(s.tg_token, s.tg_chat, f"✅ mtb: проверка уведомлений ({req.username})")
        except Exception as exc:  # noqa: BLE001
            raise ApiError(502, str(exc)) from exc
        return {"ok": True}

    # ================================================================ пользователи

    @route("GET", "/api/users", role="admin")
    def users_list(self, req: Request):
        return [{"id": r["id"], "username": r["username"], "role": r["role"],
                 "password_set": r["password_hash"] is not None, "must_set_password": bool(r["must_set_password"]),
                 "created_at": r["created_at"], "last_login": r["last_login"]}
                for r in self.db.query("SELECT * FROM users ORDER BY username")]

    @route("POST", "/api/users", role="admin")
    def users_create(self, req: Request):
        b = req.body
        username = str(b.get("username", "")).strip()
        role = str(b.get("role", "viewer"))
        password = str(b.get("password", ""))
        if not re.fullmatch(r"[A-Za-z0-9._@-]{2,64}", username):
            raise ApiError(400, "Логин: латиница, цифры и . _ @ -, от 2 до 64 символов")
        if role not in auth.ROLES:
            raise ApiError(400, "Неизвестная роль")
        if len(password) < auth.MIN_PASSWORD:
            raise ApiError(400, f"Временный пароль — не короче {auth.MIN_PASSWORD} символов")
        try:
            with self.db.tx() as c:
                c.execute("INSERT INTO users(username, password_hash, role, must_set_password, created_at) "
                          "VALUES(?,?,?,1,?)", (username, auth.hash_password(password), role, time.time()))
        except Exception as exc:
            if "UNIQUE" in str(exc):
                raise ApiError(400, "Такой пользователь уже есть") from exc
            raise
        self.audit(req, "user_create", f"{username} ({role})")
        return {"ok": True}

    def _admins_left(self, excluding: int) -> int:
        return self.db.one("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND id<>?", (excluding,))["n"]

    @route("PUT", "/api/users/(?P<id>\\d+)", role="admin")
    def users_update(self, req: Request, id):
        role = str(req.body.get("role", ""))
        if role not in auth.ROLES:
            raise ApiError(400, "Неизвестная роль")
        row = self.db.one("SELECT * FROM users WHERE id=?", (int(id),))
        if row is None:
            raise KeyError("пользователь не найден")
        if row["role"] == "admin" and role != "admin" and not self._admins_left(row["id"]):
            raise ApiError(400, "Нельзя снять роль с последнего администратора")
        with self.db.tx() as c:
            c.execute("UPDATE users SET role=? WHERE id=?", (role, row["id"]))
        self.audit(req, "user_role", f"{row['username']}: {role}")
        return {"ok": True}

    @route("POST", "/api/users/(?P<id>\\d+)/reset", role="admin")
    def users_reset(self, req: Request, id):
        password = str(req.body.get("password", ""))
        if len(password) < auth.MIN_PASSWORD:
            raise ApiError(400, f"Временный пароль — не короче {auth.MIN_PASSWORD} символов")
        row = self.db.one("SELECT * FROM users WHERE id=?", (int(id),))
        if row is None:
            raise KeyError("пользователь не найден")
        auth.set_password(self.db, row["id"], password, must_change=True)
        with self.db.tx() as c:
            c.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
        self.audit(req, "user_reset_password", row["username"])
        return {"ok": True}

    @route("DELETE", "/api/users/(?P<id>\\d+)", role="admin")
    def users_delete(self, req: Request, id):
        row = self.db.one("SELECT * FROM users WHERE id=?", (int(id),))
        if row is None:
            raise KeyError("пользователь не найден")
        if row["id"] == req.user["id"]:
            raise ApiError(400, "Нельзя удалить самого себя")
        if row["role"] == "admin" and not self._admins_left(row["id"]):
            raise ApiError(400, "Нельзя удалить последнего администратора")
        with self.db.tx() as c:
            c.execute("DELETE FROM users WHERE id=?", (row["id"],))
        self.audit(req, "user_delete", row["username"])
        return {"ok": True}

    # ================================================================ журнал

    @route("GET", "/api/runs")
    def runs_list(self, req: Request):
        limit = min(int(req.query.get("limit", 50)), 500)
        rows = self.db.query("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))
        return {"running": RUN_LOCK.locked(), "runs": [
            {"id": r["id"], "started_at": r["started_at"], "finished_at": r["finished_at"],
             "kind": r["kind"], "user": r["user"], "devices": json.loads(r["devices"]),
             "ok": json.loads(r["ok"]), "failed": json.loads(r["failed"]),
             "changed": json.loads(r["changed"]), "warnings": json.loads(r["warnings"])} for r in rows]}

    @route("POST", "/api/runs", role="admin")
    def runs_start(self, req: Request):
        if RUN_LOCK.locked():
            raise ApiError(409, "Прогон уже идёт")
        s = self.settings()
        user = req.username
        threading.Thread(target=run_once, kwargs=dict(s=s, kind="manual", db=self.db, user=user),
                         name="manual-run", daemon=True).start()
        self.audit(req, "run_all")
        return {"ok": True, "started": True}

    @route("GET", "/api/audit", role="admin")
    def audit_list(self, req: Request):
        limit = min(int(req.query.get("limit", 200)), 1000)
        return [dict(r) for r in self.db.query("SELECT * FROM audit ORDER BY ts DESC LIMIT ?", (limit,))]

    # ================================================================ сервер

    def make_server(self) -> ThreadingHTTPServer:
        handler = type("Handler", (_Handler,), {"app": self})
        httpd = ThreadingHTTPServer(self.address, handler)
        httpd.daemon_threads = True
        if self.boot.web_tls_cert:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(self.boot.web_tls_cert, self.boot.web_tls_key)
            httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        return httpd

    def serve_forever(self) -> None:
        httpd = self.make_server()
        scheme = "https" if self.boot.web_tls_cert else "http"
        log.info("Веб-интерфейс: %s://%s:%d", scheme, *self.address)
        httpd.serve_forever()

    def start_background(self) -> threading.Thread:
        t = threading.Thread(target=self.serve_forever, name="web", daemon=True)
        t.start()
        return t


class _Handler(BaseHTTPRequestHandler):
    app: WebApp
    server_version = f"mtb/{__version__}"
    sys_version = ""
    new_session: str | None = None
    clear_session: bool = False

    def log_message(self, fmt, *args):
        log.debug("%s %s", self.address_string(), fmt % args)

    # ---------------------------------------------------------------- ответы

    def _cookie_headers(self) -> dict:
        secure = "; Secure" if self.app.boot.web_cookie_secure else ""
        if self.new_session:
            return {"Set-Cookie": f"{COOKIE}={self.new_session}; Path=/; HttpOnly; SameSite=Strict; "
                                  f"Max-Age={auth.SESSION_TTL}{secure}"}
        if self.clear_session:
            return {"Set-Cookie": f"{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{secure}"}
        return {}

    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in {**SECURITY_HEADERS, **self._cookie_headers(), **(extra or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, data, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False, default=str).encode(),
                   "application/json; charset=utf-8", {"Cache-Control": "no-store"})

    def send_bytes(self, data: bytes, filename: str) -> None:
        self._send(200, data, "application/octet-stream", {
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store"})

    def cookie_token(self) -> str | None:
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001
            return None
        return c[COOKIE].value if COOKIE in c else None

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(413, "Слишком большой запрос")
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length))
        except ValueError as exc:
            raise ApiError(400, "Некорректный JSON") from exc
        if not isinstance(data, dict):
            raise ApiError(400, "Ожидался JSON-объект")
        return data

    # ---------------------------------------------------------------- маршрутизация

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        url = urlparse(self.path)
        path = url.path
        try:
            if method == "GET" and path in STATIC:
                name = STATIC[path]
                ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
                if ctype.startswith("text/") or name.endswith(".js"):
                    ctype += "; charset=utf-8"
                self._send(200, (STATIC_DIR / name).read_bytes(), ctype, {"Cache-Control": "no-cache"})
                return
            if method != "GET" and self.headers.get("X-Requested-With") != "mtb":
                raise ApiError(403, "Нет заголовка X-Requested-With")

            for m, rx, fname, role in ROUTES:
                match = rx.match(path) if m == method else None
                if not match:
                    continue
                user = auth.session_user(self.app.db, self.cookie_token())
                if role is not None:
                    if user is None:
                        raise ApiError(401, "Требуется вход")
                    if role == "admin" and user["role"] != "admin":
                        raise ApiError(403, "Недостаточно прав")
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                req = Request(self, (), query, user)
                result = getattr(self.app, fname)(req, **match.groupdict())
                if result is not None:
                    self.send_json(result)
                return
            raise KeyError("Не найдено")
        except ApiError as exc:
            self.send_json({"error": str(exc)}, exc.status)
        except ConfigError as exc:
            self.send_json({"error": str(exc)}, 400)
        except KeyError as exc:
            self.send_json({"error": str(exc.args[0]) if exc.args else "Не найдено"}, 404)
        except PermissionError as exc:
            self.send_json({"error": str(exc)}, 403)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001
            log.exception("Ошибка обработки %s %s", method, path)
            self.send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)
