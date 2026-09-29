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
