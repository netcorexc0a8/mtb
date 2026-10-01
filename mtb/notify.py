from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)


def telegram_send(token: str, chat_id: str, text: str) -> None:
    """Отправка с исключением при ошибке (для кнопки «Проверить» в настройках)."""
    r = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True},
        timeout=15,
    )
    if not r.ok:
        try:
            desc = r.json().get("description", r.text)
        except ValueError:
            desc = r.text
        raise RuntimeError(f"Telegram: {desc[:200]}")


def telegram(token: str | None, chat_id: str | None, text: str) -> None:
    if not (token and chat_id):
        return
    try:
        telegram_send(token, chat_id, text)
    except (requests.RequestException, RuntimeError) as exc:
        log.warning("Не удалось отправить уведомление: %s", exc)


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
