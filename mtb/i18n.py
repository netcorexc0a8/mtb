"""Перевод сообщений бэкенда для английского интерфейса.

Сообщения в коде пишутся по-русски (f-строками). Здесь — английские шаблоны
для них: «{}» в русском шаблоне — подставляемая часть, она переносится в
английский шаблон в том же порядке. Перевод применяется на выходе: к ошибкам
API, журналу запусков, результатам проверок и отчёту probe, а также к
уведомлениям в Telegram, если выбран английский язык уведомлений.
"""
from __future__ import annotations

import re

EN: dict[str, str] = {
    # ---- web.py
    "удалено {}, ошибок {}": "deleted {}, errors {}",
    "{} из {}: {}": "{} from {}: {}",
    "Слишком много попыток. Подождите 15 минут.": "Too many attempts. Wait 15 minutes.",
    "Неверный логин или пароль": "Invalid username or password",
    "Для этого пользователя смена пароля при входе не требуется": "This user does not need to set a password at login",
    "Неверный текущий (временный) пароль": "Invalid current (temporary) password",
    "первый вход": "first login",
    "временный пароль": "temporary password",
    "Неверный текущий пароль": "Invalid current password",
    "Неизвестное устройство": "Unknown device",
    "Не больше {} за раз": "No more than {} at a time",
    "Восстановление выключено (Настройки → Веб-интерфейс)": "Restore is disabled (Settings → Web interface)",
    "Устройства нет в списке устройств": "The device is not in the device list",
    "устройство не найдено": "device not found",
    "Укажите адрес": "Enter an address",
    "Сначала сохраните токен бота и chat_id": "Save the bot token and chat_id first",
    "✅ mtb: проверка уведомлений ({})": "✅ mtb: notification test ({})",
    "Логин: латиница, цифры и . _ @ -, от 2 до 64 символов": "Username: Latin letters, digits and . _ @ -, 2 to 64 characters",
    "Неизвестная роль": "Unknown role",
    "Временный пароль — не короче {} символов": "Temporary password must be at least {} characters",
    "пользователь не найден": "user not found",
    "Нельзя снять роль с последнего администратора": "Cannot demote the last administrator",
    "Нельзя удалить самого себя": "You cannot delete yourself",
    "Нельзя удалить последнего администратора": "Cannot delete the last administrator",
    "Прогон уже идёт": "A run is already in progress",
    "Слишком большой запрос": "Request too large",
    "Ожидался JSON-объект": "A JSON object was expected",
    "Не найдено": "Not found",
    "Некорректный JSON": "Invalid JSON",
    "Нет заголовка X-Requested-With": "Missing X-Requested-With header",
    "с ошибками": "with errors",
    "ошибка": "error",
    "Такой пользователь уже есть": "This user already exists",
    "Требуется вход": "Login required",
    "Недостаточно прав": "Insufficient permissions",
    # ---- config.py
    "Укажите пароль пользователя на роутере": "Enter the router user's password",
    "Параллельных устройств — от 1 до 32": "Parallel devices: 1 to 32",
    "Хранение — git или snapshots": "Storage must be git or snapshots",
    "Срок хранения ≥ 0 дней, минимум снимков ≥ 1": "Retention ≥ 0 days, minimum snapshots ≥ 1",
    "CA Gitea должен быть в формате PEM": "The Gitea CA must be in PEM format",
    "Для Telegram нужны и токен бота, и chat_id": "Telegram needs both a bot token and a chat_id",
    "Имя: латиница, цифры, точка, дефис, подчёркивание (до 64 символов)": "Name: Latin letters, digits, dot, hyphen, underscore (up to 64 characters)",
    "{}: не указан адрес": "{}: no address specified",
    "{}: не указан пользователь": "{}: no user specified",
    "{}: transport должен быть sftp, api или ssh": "{}: transport must be sftp, api or ssh",
    "{}: api_binary должен быть base64, raw или skip": "{}: api_binary must be base64, raw or skip",
    "{}: формат сертификатов — p12 или pem": "{}: certificate format must be p12 or pem",
    "{}: при api_binary=skip сертификаты можно выгружать только в pem": "{}: with api_binary=skip certificates can only be exported as pem",
    "{}: размер куска base64 — от 3072 до 32768": "{}: base64 chunk size must be 3072 to 32768",
    "{}: таймаут — от 1 до 600 секунд": "{}: timeout must be 1 to 600 seconds",
    "{}: CA должен быть в формате PEM": "{}: the CA must be in PEM format",
    "{}: для API-SSL укажите отпечаток, CA или отключите проверку": "{}: for API-SSL, set a fingerprint or a CA, or disable verification",
    "Неизвестная настройка: {}": "Unknown setting: {}",
    "Неизвестный часовой пояс: {}": "Unknown time zone: {}",
    "Расписание: {}": "Schedule: {}",
    "Push в Gitea работает только с хранением git": "Gitea push works only with git storage",
    "URL репозитория Gitea должен начинаться с https://": "The Gitea repository URL must start with https://",
    "Для Gitea нужны пользователь и токен": "Gitea needs a user and a token",
    "{}: неверный порт {}": "{}: invalid port {}",
    "{}: неизвестная кодировка {}": "{}: unknown encoding {}",
    "{}: отпечаток должен быть SHA-256 (64 hex-символа)": "{}: the fingerprint must be SHA-256 (64 hex characters)",
    "{}: сертификаты — all, none или список имён": "{}: certificates must be all, none or a list of names",
    "Устройство с именем {} уже есть": "A device named {} already exists",
    "{}: неверное значение": "{}: invalid value",
    "{}: ожидалось целое число": "{}: an integer was expected",
    # ---- auth.py
    "Пароли не совпадают": "Passwords do not match",
    "Пароль должен быть не короче {} символов": "The password must be at least {} characters",
    "Пароль не должен совпадать с логином": "The password must not match the username",
    "Пароль слишком простой": "The password is too simple",
    # ---- runner.py (журнал и Telegram)
    "Не задан пароль шифрования бэкапов (Настройки → Хранение)": "No backup encryption passphrase set (Settings → Storage)",
    "ручной бэкап": "manual backup",
    "{} {} {}: {}/{} успешно": "{} {} {}: {}/{} succeeded",
    "нет включённых устройств": "no enabled devices",
    "push в Gitea: {}": "Gitea push: {}",
    "Изменения: ": "Changes: ",
    "❌ mtb: ошибка хранилища {}: {}": "❌ mtb: storage error {}: {}",
    "ротация снимков": "snapshot rotation",
    # ---- mikrotik.py
    "Файлы не готовы: ожидалось {}, есть {}": "Files not ready: expected {}, found {}",
    "нужен RouterOS 7.13+ для /file/read": "RouterOS 7.13+ is required for /file/read",
    "Не получен экспорт конфигурации": "The configuration export was not received",
    "Не получен system.backup": "system.backup was not received",
    "Получено {} файлов сертификатов из {}": "Received {} of {} certificate files",
    "RouterOS: {} (команда: {})": "RouterOS: {} (command: {})",
    "Неожиданный вывод /export: {}": "Unexpected /export output: {}",
    "{}: неоднозначный ответ /file/read для крошечного файла": "{}: ambiguous /file/read response for a tiny file",
    "{}: получено {} байт вместо {} на смещении {}": "{}: received {} bytes instead of {} at offset {}",
    "transport: api требует RouterOS 7.13+ (/file/read)": "transport: api requires RouterOS 7.13+ (/file/read)",
    "{}: отпечаток TLS не совпал, получен {}": "{}: TLS fingerprint mismatch, got {}",
    "{}: некорректный base64 на смещении {}: {}": "{}: invalid base64 at offset {}: {}",
    "{}: размер {} вместо {}": "{}: size {} instead of {}",
    "{}: прочитано {} байт вместо {}": "{}: read {} bytes instead of {}",
    "(пусто)": "(empty)",
    "не хватает политик: {}": "missing policies: {}",
    # ---- probe.py
    "DIFF: строк {} против {}, первое расхождение в строке {}": "DIFF: {} lines vs {}, first difference at line {}",
    "бинарные файлы через API не читаются; без SSH можно работать в режиме transport: api, api_binary: skip, cert_format: pem (без system.backup)":
        "binary files cannot be read via the API; without SSH you can use transport: api, api_binary: skip, cert_format: pem (no system.backup)",
    "нет сертификатов с приватным ключом — .p12/PEM не проверялись": "no certificates with a private key — .p12/PEM were not tested",
    "пропущен": "skipped",
    "RouterOS {}: /file/read появился в 7.13, режим api недоступен": "RouterOS {}: /file/read appeared in 7.13, api mode is unavailable",
    "без SFTP-эталона .backup проверен только по размеру и совпадению результатов разных способов":
        "without an SFTP reference, .backup was checked only by size and agreement between methods",
    "/export через stdout SSH (transport: ssh): {}": "/export via SSH stdout (transport: ssh): {}",
    "ОШИБКА: {}": "ERROR: {}",
    "Рекомендация для настроек устройства → {}": "Recommended device settings → {}",
    "Рекомендации нет: ни SFTP, ни API не прошли проверку": "No recommendation: neither SFTP nor the API passed the check",
    "не похоже на экспорт": "does not look like an export",
    "{} байт вместо {}": "{} bytes instead of {}",
    "не совпадает с SFTP": "differs from SFTP",
    "способы чтения дали разные данные": "read methods returned different data",
    "{}: эталон по SFTP не разобрался ({}) — для .p12 это бывает из-за устаревших алгоритмов, на результат не влияет":
        "{}: the SFTP reference could not be parsed ({}) — for .p12 this happens with legacy algorithms and does not affect the result",
    "{} байт": "{} bytes",
    "/file/read: есть": "/file/read: yes",
    "/file/read: нет": "/file/read: no",
    "файл": "file",
    "размер": "size",
    # ---- storage.py / catalog.py
    "git не установлен: установите git или задайте GIT_HISTORY=false (для push в Gitea git обязателен)":
        "git is not installed: install git or switch to snapshots storage (git is required for Gitea push)",
    "бэкап не найден": "backup not found",
    "неверный идентификатор": "invalid identifier",
    "файл не найден": "file not found",
    "этот бэкап нельзя удалить: он часть истории git": "this backup cannot be deleted: it is part of the git history",
    "Язык уведомлений — ru или en": "Notification language must be ru or en",
    # ---- проверка устройства
    "SSH ok, SFTP ok": "SSH ok, SFTP ok",
}

_WORD = r"[0-9A-Za-zА-Яа-яЁё_]"


def _compile(ru: str) -> re.Pattern:
    parts = ru.split("{}")
    rx = ""
    for i, lit in enumerate(parts):
        rx += re.escape(lit)
        if i < len(parts) - 1:
            rx += r"([^\n]*)" if i == len(parts) - 2 and parts[-1] == "" else r"([^\n]+?)"
    # Фраза без подстановок не должна цепляться за часть другого слова
    if ru[:1].isalpha():
        rx = f"(?<!{_WORD})" + rx
    if ru[-1:].isalpha():
        rx += f"(?!{_WORD})"
    return re.compile(rx)


_TABLE = sorted(((len(ru), _compile(ru), en) for ru, en in EN.items()), key=lambda x: -x[0])


def translate(text, lang: str | None):
    """Переводит строку (или вложенные list/dict) на lang. Для ru — без изменений."""
    if lang != "en" or text is None:
        return text
    if isinstance(text, list):
        return [translate(x, lang) for x in text]
    if isinstance(text, dict):
        return {k: translate(v, lang) for k, v in text.items()}
    if not isinstance(text, str) or not re.search("[А-Яа-яЁё]", text):
        return text
    for _, rx, en in _TABLE:
        if rx.search(text):
            text = rx.sub(lambda m, en=en: en.format(*m.groups()), text)
    return text
