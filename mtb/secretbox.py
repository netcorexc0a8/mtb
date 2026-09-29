"""Шифрование секретов в базе (Fernet: AES-128-CBC + HMAC-SHA256).

Ключ создаётся при первом запуске в DATA_DIR/secret.key с правами 0600.
Без этого файла зашифрованные пароли из базы не прочитать — копируйте
его вместе с mtb.db.
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

PREFIX = "fernet:"


class SecretBox:
    def __init__(self, key_path: Path):
        key_path = Path(key_path)
        if not key_path.exists():
            key_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as fh:
                fh.write(Fernet.generate_key())
        self._f = Fernet(key_path.read_bytes().strip())

    def encrypt(self, value: str | None) -> str:
        if not value:
            return ""
        return PREFIX + self._f.encrypt(value.encode()).decode()

    def decrypt(self, value: str | None) -> str:
        if not value:
            return ""
        if not value.startswith(PREFIX):
            raise ValueError("значение не зашифровано")
        try:
            return self._f.decrypt(value[len(PREFIX):].encode()).decode()
        except InvalidToken as exc:
            raise ValueError("не удалось расшифровать секрет: другой secret.key?") from exc
