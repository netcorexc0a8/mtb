"""Уведомления: список URL в формате Shoutrrr (как в Beszel и Watchtower).

  telegram://ТОКЕН@telegram?chats=ID[,ID]        токен бота вида 123456:ABC…, ID — chat_id,
                                                 @канал или chat_id:thread_id (тема)
  discord://ТОКЕН@ID_ВЕБХУКА                     из https://discord.com/api/webhooks/ID/ТОКЕН
  slack://hook:A-B-C@webhook                     вебхук https://hooks.slack.com/services/A/B/C
  slack://xoxb:ТОКЕН@КАНАЛ                       бот-токен xoxb-…
  mattermost://[имя@]сервер[:порт]/ТОКЕН[/канал] входящий вебхук
  matrix://пользователь:пароль@сервер[:порт]/?rooms=!id,#alias:сервер
                                                 без пользователя пароль — это access token
  ntfy://[пользователь:пароль@]сервер[:порт]/ТОПИК   без пользователя пароль — токен tk_…
  gotify://сервер[:порт][/путь]/ТОКЕН_ПРИЛОЖЕНИЯ
  pushover://shoutrrr:API_ТОКЕН@КЛЮЧ_ПОЛЬЗОВАТЕЛЯ/[?devices=a,b]
  smtp://[пользователь:пароль@]сервер[:порт]/?from=mtb@example.com&to=a@example.com[,b@…]
                                                 encryption=auto|none|starttls|tls
  generic://сервер[:порт]/путь                   webhook: текст в теле POST;
                                                 template=json — {"title": …, "message": …};
                                                 @Заголовок=значение — HTTP-заголовки;
                                                 generic+http://… — без TLS

Общие параметры: title=… (заголовок там, где он есть), disabletls=yes (http вместо
https для своих серверов), insecure=yes (не проверять сертификат — самоподписанный
в закрытом контуре). Спецсимволы в токенах и паролях кодируются как в URL (%40 = @).
"""
from __future__ import annotations

import logging
import smtplib
import ssl
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

import requests

log = logging.getLogger(__name__)

SERVICES = {
    "telegram": "Telegram", "discord": "Discord", "slack": "Slack", "mattermost": "Mattermost",
    "matrix": "Matrix", "ntfy": "ntfy", "gotify": "Gotify", "pushover": "Pushover",
    "smtp": "E-mail", "generic": "Webhook",
}
# параметры, которые generic не передаёт дальше в адрес вебхука
_OWN_PARAMS = {"title", "disabletls", "insecure", "template", "titlekey", "messagekey", "method"}
MAX_URLS = 20


class NotifyError(ValueError):
    """Ошибка в URL уведомления или при отправке — показывается пользователю как есть."""


@dataclass
class Target:
    service: str
    userinfo: str                         # всё до @, раскодированное (токен Telegram, Discord)
    user: str
    password: str
    host: str                             # регистр сохраняется: в нём бывают токены
    port: int | None
    path: list[str]
    params: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return SERVICES[self.service]

    def flag(self, key: str) -> bool:
        return self.params.get(key, "").lower() in ("yes", "true", "1", "on")

    def base(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{'http' if self.flag('disabletls') else 'https'}://{host}{f':{self.port}' if self.port else ''}"

    def items(self, key: str) -> list[str]:
        return [x.strip() for x in self.params.get(key, "").split(",") if x.strip()]


def parse(url: str) -> Target:
    url = (url or "").strip()
    if not url:
        raise NotifyError("Пустой URL уведомления")
    p = urlsplit(url, allow_fragments=False)            # # в rooms=#alias — не фрагмент
    scheme = p.scheme.lower()
    params: dict = {}
    if scheme in ("generic+http", "generic+https"):
        params["disabletls"] = "yes" if scheme == "generic+http" else "no"
        scheme = "generic"
    if scheme not in SERVICES:
        raise NotifyError(f"Неизвестный сервис уведомлений: {p.scheme or url[:20]}")
    headers = {}
    for k, v in parse_qsl(p.query, keep_blank_values=True):
        if k.startswith("@") and len(k) > 1:
            headers[k[1:]] = v
        else:
            params[k.lower()] = v
    userinfo, _, hostport = p.netloc.rpartition("@")
    user, _, password = userinfo.partition(":")
    host, port = hostport, None
    if hostport.startswith("["):                           # IPv6
        host, _, rest = hostport[1:].partition("]")
        if rest.startswith(":") and rest[1:]:
            port = rest[1:]
    elif ":" in hostport:
        host, _, port = hostport.rpartition(":")
    if port is not None and not (port.isdigit() and 0 < int(port) < 65536):
        raise NotifyError(f"{SERVICES[scheme]}: неверный порт")
    t = Target(scheme, unquote(userinfo), unquote(user), unquote(password), unquote(host),
               int(port) if port else None, [unquote(x) for x in p.path.split("/") if x], params, headers)
    problem = _CHECKS[scheme](t)
    if problem:
        raise NotifyError(f"{t.name}: {problem}")
    return t


def _slack_webhook(t: Target) -> str | None:
    if t.user == "hook" and t.password:
        parts = t.password.replace("/", "-").split("-")
    elif not t.userinfo and t.host and len(t.path) == 2:
        parts = [t.host, *t.path]
    else:
        return None
    return "/".join(parts) if len(parts) == 3 and all(parts) else None


_CHECKS = {
    "telegram": lambda t: None if ":" in t.userinfo and t.items("chats") else "нужны токен бота и chats=",
    "discord": lambda t: None if t.userinfo and t.host else "нужны токен и ID вебхука",
    "slack": lambda t: None if _slack_webhook(t) or (t.user == "xoxb" and t.password and t.host)
    else "нужен вебхук (hook:A-B-C@webhook) или бот-токен (xoxb:ТОКЕН@КАНАЛ)",
    "mattermost": lambda t: None if t.host and t.path else "нужны сервер и токен вебхука",
    "matrix": lambda t: None if t.host and t.password and t.items("rooms") else "нужны сервер, пароль или токен и rooms=",
    "ntfy": lambda t: None if t.host and t.path else "нужны сервер и топик",
    "gotify": lambda t: None if t.host and t.path else "нужны сервер и токен приложения",
    "pushover": lambda t: None if t.password and t.host else "нужны API-токен и ключ пользователя",
    "smtp": lambda t: None if t.host and t.items("from") and t.items("to") else "нужны сервер, from= и to=",
    "generic": lambda t: None if t.host else "нужен адрес",
}


def label(url: str) -> dict:
    """Описание URL для веб-интерфейса — без токенов и паролей."""
    try:
        t = parse(url)
    except NotifyError as exc:
        return {"service": "?", "label": str(exc)}
    srv = t.host + (f":{t.port}" if t.port else "")
    info = {
        "telegram": lambda: ", ".join(t.items("chats")),
        "discord": lambda: "",
        "slack": lambda: "" if _slack_webhook(t) else f"#{t.host}",
        "mattermost": lambda: srv + (f" #{t.path[1]}" if len(t.path) > 1 else ""),
        "matrix": lambda: f"{srv} · {', '.join(t.items('rooms'))}",
        "ntfy": lambda: f"{srv}/{t.path[-1][:3]}…",         # топик на ntfy.sh — по сути пароль
        "gotify": lambda: srv,
        "pushover": lambda: ", ".join(t.items("devices")),
        "smtp": lambda: f"{srv} → {', '.join(t.items('to'))}",
        "generic": lambda: srv,
    }[t.service]()
    return {"service": t.name, "label": info}


# ---------------------------------------------------------------- отправка

def _http(t: Target, method: str, url: str, **kw) -> requests.Response:
    kw.setdefault("timeout", 15)
    if t.flag("insecure"):
        kw["verify"] = False
    try:
        r = requests.request(method, url, **kw)
    except requests.RequestException as exc:
        raise NotifyError(f"{t.name}: {type(exc).__name__}: {exc}") from exc
    if not r.ok:
        try:
            body = r.json()
            desc = body.get("description") or body.get("message") or body.get("error") or r.text
        except (ValueError, AttributeError):
            desc = r.text
        raise NotifyError(f"{t.name}: HTTP {r.status_code} {str(desc)[:200]}".rstrip())
    return r


def _telegram(t: Target, title: str, text: str) -> None:
    for chat in t.items("chats"):
        body = {"chat_id": chat, "text": text[:4096], "disable_web_page_preview": True}
        if not chat.startswith("@") and ":" in chat:
            body["chat_id"], _, thread = chat.partition(":")
            body["message_thread_id"] = int(thread) if thread.isdigit() else thread
        _http(t, "POST", f"https://api.telegram.org/bot{t.userinfo}/sendMessage", json=body)


def _discord(t: Target, title: str, text: str) -> None:
    body = {"content": text[:2000]}
    if t.params.get("username"):
        body["username"] = t.params["username"]
    _http(t, "POST", f"https://discord.com/api/webhooks/{t.host}/{quote(t.userinfo, safe='')}", json=body)


def _slack(t: Target, title: str, text: str) -> None:
    hook = _slack_webhook(t)
    if hook:
        _http(t, "POST", f"https://hooks.slack.com/services/{hook}", json={"text": text})
        return
    r = _http(t, "POST", "https://slack.com/api/chat.postMessage", json={"channel": t.host, "text": text},
              headers={"Authorization": f"Bearer xoxb-{t.password}"})
    body = r.json()
    if not body.get("ok"):
        raise NotifyError(f"Slack: {body.get('error', r.text[:200])}")


def _mattermost(t: Target, title: str, text: str) -> None:
    body = {"text": text}
    if len(t.path) > 1:
        body["channel"] = t.path[1]
    if t.userinfo:
        body["username"] = t.userinfo
    _http(t, "POST", f"{t.base()}/hooks/{quote(t.path[0], safe='')}", json=body)


def _matrix(t: Target, title: str, text: str) -> None:
    api = f"{t.base()}/_matrix/client/v3"
    token = t.password
    if t.user:
        r = _http(t, "POST", f"{api}/login", json={
            "type": "m.login.password", "identifier": {"type": "m.id.user", "user": t.user},
            "password": t.password, "initial_device_display_name": "mtb"})
        token = r.json().get("access_token", "")
    auth = {"Authorization": f"Bearer {token}"}
    try:
        for room in t.items("rooms"):
            if room.startswith("#"):
                room = _http(t, "GET", f"{api}/directory/room/{quote(room, safe='')}", headers=auth).json()["room_id"]
            _http(t, "PUT", f"{api}/rooms/{quote(room, safe='')}/send/m.room.message/{uuid.uuid4().hex}",
                  json={"msgtype": "m.text", "body": text}, headers=auth)
    finally:
        if t.user:                                   # не копить «устройства» входа на сервере
            try:
                _http(t, "POST", f"{api}/logout", json={}, headers=auth)
            except NotifyError:
                pass


def _ntfy(t: Target, title: str, text: str) -> None:
    # заголовок и прочее — параметрами запроса: в HTTP-заголовках не-ASCII ненадёжен
    query = {"title": title, **{k: t.params[k] for k in ("priority", "tags", "click") if t.params.get(k)}}
    headers, auth = {}, None
    if t.user:
        auth = (t.user, t.password)
    elif t.password:
        headers["Authorization"] = f"Bearer {t.password}"
    path = "/".join(quote(x, safe="") for x in t.path)
    _http(t, "POST", f"{t.base()}/{path}?{urlencode(query)}", data=text.encode("utf-8"), headers=headers, auth=auth)


def _gotify(t: Target, title: str, text: str) -> None:
    sub = "".join(f"/{quote(x, safe='')}" for x in t.path[:-1])
    try:
        priority = int(t.params.get("priority", 5))
    except ValueError as exc:
        raise NotifyError("Gotify: priority должен быть числом") from exc
    _http(t, "POST", f"{t.base()}{sub}/message", json={"title": title, "message": text, "priority": priority},
          headers={"X-Gotify-Key": t.path[-1]})


def _pushover(t: Target, title: str, text: str) -> None:
    data = {"token": t.password, "user": t.host, "title": title[:250], "message": text[:1024]}
    if t.items("devices"):
        data["device"] = ",".join(t.items("devices"))
    if t.params.get("priority"):
        data["priority"] = t.params["priority"]
    _http(t, "POST", "https://api.pushover.net/1/messages.json", data=data)


_SMTP_MODES = {"auto": "auto", "none": "none", "starttls": "starttls", "explicittls": "starttls",
               "tls": "tls", "ssl": "tls", "implicittls": "tls"}


def _smtp(t: Target, title: str, text: str) -> None:
    mode = _SMTP_MODES.get(t.params.get("encryption", "auto").lower())
    if not mode:
        raise NotifyError("E-mail: encryption — auto, none, starttls или tls")
    port = t.port or (465 if mode == "tls" else 587 if mode == "starttls" else 25)
    if mode == "auto":
        mode = "tls" if port == 465 else "auto"
    ctx = ssl.create_default_context()
    if t.flag("insecure"):
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    msg = EmailMessage()
    msg["Subject"] = t.params.get("subject") or title
    msg["From"] = t.params["from"]
    msg["To"] = ", ".join(t.items("to"))
    msg.set_content(text)
    try:
        if mode == "tls":
            conn = smtplib.SMTP_SSL(t.host, port, timeout=20, context=ctx)
        else:
            conn = smtplib.SMTP(t.host, port, timeout=20)
        with conn:
            conn.ehlo()
            if mode == "starttls" or (mode == "auto" and conn.has_extn("starttls")):
                conn.starttls(context=ctx)
                conn.ehlo()
            if t.user:
                conn.login(t.user, t.password)
            conn.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        raise NotifyError(f"E-mail: {type(exc).__name__}: {exc}") from exc


def _generic(t: Target, title: str, text: str) -> None:
    path = "/".join(quote(x, safe="") for x in t.path)
    rest = {k: v for k, v in t.params.items() if k not in _OWN_PARAMS}
    url = f"{t.base()}/{path}" + (f"?{urlencode(rest)}" if rest else "")
    method = t.params.get("method", "POST").upper()
    headers = dict(t.headers)
    if t.params.get("template", "").lower() == "json":
        body = {t.params.get("titlekey", "title"): title, t.params.get("messagekey", "message"): text}
        _http(t, method, url, json=body, headers=headers)
    else:
        headers.setdefault("Content-Type", "text/plain; charset=utf-8")
        _http(t, method, url, data=text.encode("utf-8"), headers=headers)


_SENDERS = {
    "telegram": _telegram, "discord": _discord, "slack": _slack, "mattermost": _mattermost,
    "matrix": _matrix, "ntfy": _ntfy, "gotify": _gotify, "pushover": _pushover,
    "smtp": _smtp, "generic": _generic,
}


def send_one(url: str, text: str, title: str = "mtb") -> None:
    """Отправка с исключением при ошибке (для кнопки «Проверить» в настройках)."""
    t = parse(url)
    _SENDERS[t.service](t, t.params.get("title") or title, text)


def send(urls: list[str], text: str, title: str = "mtb") -> list[str]:
    """Отправка во все каналы. Ошибка одного канала не мешает остальным; возвращает ошибки."""
    errors = []
    for url in urls or []:
        try:
            send_one(url, text, title)
        except Exception as exc:  # noqa: BLE001 — уведомление не должно ронять прогон
            msg = str(exc) if isinstance(exc, NotifyError) else f"{type(exc).__name__}: {exc}"
            log.warning("Не удалось отправить уведомление: %s", msg)
            errors.append(msg)
    return errors


def telegram_url(token: str, chat: str) -> str:
    """Прежние настройки Telegram (токен + chat_id) в виде URL."""
    return f"telegram://{quote(token, safe=':')}@telegram?chats={quote(chat, safe='@-:,')}"


# ---------------------------------------------------------------- шаблоны сообщений

import re as _re

# Переменные шаблона. Значения подставляются на языке уведомлений.
TEMPLATE_VARS = ("icon", "title", "kind", "date", "time", "ok", "total", "failed_count",
                 "changed_count", "devices", "changes", "errors", "warnings", "version")

PRESETS = {
    "ru": {
        "detailed": "{icon} {title} {date} {time}: {ok}/{total} успешно\n{changes}\n{errors}\n{warnings}",
        "short": "{icon} mtb {date} {time}: {ok}/{total}, изменений {changed_count}, ошибок {failed_count}",
        "errors": "{icon} mtb {date} {time}: ошибок {failed_count}\n{errors}\n{warnings}",
    },
    "en": {
        "detailed": "{icon} {title} {date} {time}: {ok}/{total} succeeded\n{changes}\n{errors}\n{warnings}",
        "short": "{icon} mtb {date} {time}: {ok}/{total}, changed {changed_count}, errors {failed_count}",
        "errors": "{icon} mtb {date} {time}: errors: {failed_count}\n{errors}\n{warnings}",
    },
}

_VAR_RE = _re.compile(r"\{(\w+)\}")


def template_unknown_vars(template: str) -> list[str]:
    return sorted({m for m in _VAR_RE.findall(template or "") if m not in TEMPLATE_VARS})


def render(template: str, ctx: dict) -> str:
    """Подставляет {переменные}. Строки, ставшие пустыми (нет изменений, нет ошибок), убираются."""
    lines = []
    for line in (template or "").splitlines():
        had_vars = bool(_VAR_RE.search(line))
        out = _VAR_RE.sub(lambda m: str(ctx.get(m.group(1), m.group(0))), line)
        if had_vars and not out.strip():
            continue
        lines.append(out)
    return "\n".join(lines).strip()[:4000]


def report_context(lang: str, *, kind: str, started, ok: list, failed: dict, changed: dict,
                   warnings: list, devices: list, version: str) -> dict:
    """Значения переменных для отчёта о прогоне на языке уведомлений."""
    en = lang == "en"
    icon = "✅" if not (failed or warnings) else ("⚠️" if ok else "❌")
    manual = kind == "manual"
    changes = "; ".join(f"{n} ({', '.join(c)})" for n, c in sorted(changed.items()))
    return {
        "icon": icon,
        "title": ("manual backup" if en else "ручной бэкап") if manual else "mtb",
        "kind": ("manual" if en else "ручной") if manual else ("scheduled" if en else "по расписанию"),
        "date": started.strftime("%d.%m.%Y"), "time": started.strftime("%H:%M"),
        "ok": len(ok), "total": len(devices), "failed_count": len(failed), "changed_count": len(changed),
        "devices": ", ".join(devices),
        "changes": f"{'Changes' if en else 'Изменения'}: {changes}" if changes else "",
        "errors": "\n".join(f"• {n}: {e}" for n, e in sorted(failed.items())),
        "warnings": "\n".join(f"• {w}" for w in warnings),
        "version": version,
    }


def sample_context(lang: str, version: str) -> dict:
    from datetime import datetime
    return report_context(
        lang, kind="scheduled", started=datetime.now(), ok=["core-rtr1", "branch-rtr2"],
        failed={"edge-rtr3": "TimeoutError: timed out"}, changed={"core-rtr1": ["config"]},
        warnings=[], devices=["core-rtr1", "branch-rtr2", "edge-rtr3"], version=version)


def should_notify(when: str, failed: dict, warnings: list, changed: dict) -> bool:
    if when == "always":
        return True
    if when == "errors":
        return bool(failed or warnings)
    return bool(failed or warnings or changed)          # changes — при ошибках и изменениях
