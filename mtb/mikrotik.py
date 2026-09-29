"""Работа с RouterOS: команды через API-SSL, файлы — по SFTP или через API.

Транспорты (поле transport в настройках устройства):
  sftp  команды по API, файлы по SFTP (порт 22). Надёжно для любых файлов.
  ssh   всё по SSH (порт 22), без API: конфиг читается прямо из stdout
        команды /export — на роутере не создаётся файлов. Сертификаты и
        system.backup (если не config_only) — файлы по SFTP в той же сессии.
  api   всё через API-SSL (порт 8729), файлы читаются командой /file/read
        (RouterOS 7.13+). Текстовые файлы читаются напрямую, бинарные
        (.backup, .p12) — способом api_binary:
          base64  роутер кодирует кусок файла в base64 (/execute + :convert)
          raw     сырые байты через отдельное соединение в latin-1
          skip    бинарные файлы не забираются, сертификаты — в PEM

Проверить, что работает на конкретном роутере: mtb probe -d NAME
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import re
import ssl
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import paramiko
from librouteros import connect
from librouteros.exceptions import LibRouterosError, TrapError

from .config import Device

log = logging.getLogger(__name__)

PREFIX = "mtbk-"
CFG_FILE = f"{PREFIX}cfg"        # -> mtbk-cfg.rsc
SYS_FILE = f"{PREFIX}sys"        # -> mtbk-sys.backup
CERT_FILE = f"{PREFIX}cert-"     # -> mtbk-cert-<name>.p12 | .crt + .key

TEXT_EXT = (".rsc", ".crt", ".key")
BINARY_EXT = (".backup", ".p12")

READ_CHUNK = 32768               # максимум /file/read за один вызов
MIN_FILE_READ = (7, 13)

_hostkeys_lock = threading.Lock()


class FingerprintMismatch(ssl.SSLError):
    pass


@dataclass
class DeviceResult:
    name: str
    identity: str = ""
    version: str = ""
    config: bytes = b""
    backup: bytes = b""
    certs: dict[str, bytes] = field(default_factory=dict)   # имя файла -> содержимое
    cert_index: list[dict] = field(default_factory=list)
    config_only: bool = False


def parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version.split(" ")[0])[:3])


# ---------------------------------------------------------------- TLS

def _norm_fp(fp: str) -> str:
    return fp.replace(":", "").replace(" ", "").lower()


def make_ssl_wrapper(dev: Device):
    if dev.tls_ca:
        ctx = ssl.create_default_context(cadata=dev.tls_ca)      # PEM из базы
        # У самоподписанного сертификата RouterOS обычно нет SAN с IP
        ctx.check_hostname = False
    else:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if dev.tls_legacy:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")

    expected = _norm_fp(dev.tls_fingerprint) if dev.tls_fingerprint else None

    def wrapper(sock):
        tls = ctx.wrap_socket(sock, server_hostname=dev.host)
        if expected:
            actual = hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()
            if actual != expected:
                tls.close()
                raise FingerprintMismatch(
                    f"{dev.name}: отпечаток TLS не совпал, получен {actual}")
        return tls

    return wrapper


def open_api(dev: Device, encoding: str | None = None):
    return connect(
        host=dev.host, username=dev.username, password=dev.password,
        port=dev.api_port, timeout=dev.timeout, encoding=encoding or dev.encoding,
        ssl_wrapper=make_ssl_wrapper(dev),
    )


def fetch_fingerprint(host: str, port: int = 8729, timeout: float = 10) -> dict:
    """Возвращает отпечаток и сведения о TLS-сертификате (без проверки)."""
    import socket

    from cryptography import x509

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    cert = x509.load_der_x509_certificate(der)
    fp = hashlib.sha256(der).hexdigest()
    return {
        "fingerprint": ":".join(fp[i:i + 2] for i in range(0, len(fp), 2)).upper(),
        "subject": cert.subject.rfc4514_string(),
        "not_after": cert.not_valid_after_utc.strftime("%Y-%m-%d"),
        "key_bits": getattr(cert.public_key(), "key_size", "?"),
        "pem": ssl.DER_cert_to_PEM_cert(der),
    }


# ---------------------------------------------------------------- SFTP

def open_ssh(dev: Device, known_hosts: Path) -> paramiko.SSHClient:
    """SSH с TOFU: первый ключ хоста запоминается, смена ключа -> ошибка."""
    client = paramiko.SSHClient()
    if known_hosts.exists():
        client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        dev.host, port=dev.ssh_port, username=dev.username, password=dev.password,
        timeout=dev.timeout, banner_timeout=dev.timeout, auth_timeout=dev.timeout,
        look_for_keys=False, allow_agent=False,
    )
    key = client.get_transport().get_remote_server_key()
    hk_name = dev.host if dev.ssh_port == 22 else f"[{dev.host}]:{dev.ssh_port}"
    with _hostkeys_lock:
        hk = paramiko.HostKeys()
        if known_hosts.exists():
            hk.load(str(known_hosts))
        if hk.lookup(hk_name) is None:
            hk.add(hk_name, key.get_name(), key)
            known_hosts.parent.mkdir(parents=True, exist_ok=True)
            hk.save(str(known_hosts))
            log.warning("%s: сохранён новый SSH host key %s", dev.name, key.get_base64()[:24])
    return client


def sftp_read_all(dev: Device, known_hosts: Path, paths: list[str]) -> dict[str, bytes]:
    ssh = open_ssh(dev, known_hosts)
    try:
        sftp = ssh.open_sftp()
        out = {}
        for path in paths:
            with sftp.open(path, "rb") as fh:
                out[path] = fh.read()
        return out
    finally:
        ssh.close()


# ---------------------------------------------------------------- SSH-команды

# RouterOS сообщает об ошибках текстом, а не кодом возврата
FAILURE_RE = re.compile(
    r"(^|\n)\s*(syntax error|bad command name|expected end of command|no such item|"
    r"failure:|input does not match any value|invalid value|not enough permissions)", re.I)


def ros_quote(value: str) -> str:
    """Строка в кавычках для консоли RouterOS."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


class SshSession:
    """Одна SSH-сессия: консольные команды через exec и SFTP для файлов."""

    def __init__(self, dev: Device, known_hosts: Path):
        self.dev = dev
        self.client = open_ssh(dev, known_hosts)
        self._sftp = None

    @property
    def sftp(self):
        if self._sftp is None:
            self._sftp = self.client.open_sftp()
        return self._sftp

    def run_bytes(self, command: str, timeout: float | None = None) -> bytes:
        timeout = timeout or max(60.0, self.dev.timeout * 2)
        _, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        out = stdout.read() + stderr.read()
        return out.replace(b"\r\n", b"\n")

    def run(self, command: str, timeout: float | None = None, check: bool = True) -> str:
        text = self.run_bytes(command, timeout).decode(self.dev.encoding, errors="replace").strip()
        if check and FAILURE_RE.search(text):
            raise RuntimeError(f"RouterOS: {text.splitlines()[-1][:200]} (команда: {command[:80]})")
        return text

    def list_files(self, prefix: str = PREFIX) -> list[str]:
        out = self.run(f':foreach f in=[/file find where name~"(^|/){prefix}"] '
                       f'do={{:put [/file get $f name]}}')
        return [line.strip() for line in out.splitlines() if line.strip()]

    def cleanup(self, prefix: str = PREFIX) -> None:
        try:
            self.run(f'/file remove [find where name~"(^|/){prefix}"]')
        except Exception as exc:  # noqa: BLE001
            log.warning("%s: не удалось удалить временные файлы: %s", self.dev.name, exc)

    def wait_files(self, expected: int, prefix: str = PREFIX, timeout: float = 90) -> dict[str, int]:
        deadline = time.monotonic() + timeout
        prev: dict[str, int] | None = None
        while time.monotonic() < deadline:
            sizes = {}
            for name in self.list_files(prefix):
                try:
                    sizes[name] = self.sftp.stat(name).st_size or 0
                except OSError:
                    sizes[name] = 0
            if len(sizes) >= expected and all(sizes.values()) and sizes == prev:
                return sizes
            prev = sizes
            time.sleep(2)
        raise TimeoutError(f"Файлы не готовы: ожидалось {expected}, есть {list(prev or {})}")

    def read_file(self, path: str) -> bytes:
        with self.sftp.open(path, "rb") as fh:
            return fh.read()

    def cert_index(self) -> list[dict]:
        script = (':foreach c in=[/certificate find] do={:local a [/certificate get $c]; '
                  ':put (($a->"name") . "\\t" . ($a->"common-name") . "\\t" . '
                  '($a->"fingerprint") . "\\t" . ($a->"invalid-after") . "\\t" . '
                  '($a->"private-key"))}')
        rows = []
        for line in self.run(script).splitlines():
            parts = (line.split("\t") + [""] * 5)[:5]
            if not parts[0].strip():
                continue
            rows.append({
                "name": parts[0].strip(),
                "common-name": parts[1].strip(),
                "fingerprint": parts[2].strip(),
                "invalid-after": parts[3].strip(),
                "private-key": parts[4].strip().lower() in ("true", "yes"),
            })
        return rows

    def export_stdout(self) -> bytes:
        data = self.run_bytes("/export show-sensitive terse",
                              timeout=max(120.0, self.dev.timeout * 4))
        head = data.lstrip()[:200].decode(self.dev.encoding, errors="replace")
        if not head.startswith("#") or FAILURE_RE.search(head):
            raise RuntimeError(f"Неожиданный вывод /export: {head.splitlines()[0] if head else '(пусто)'}")
        return data

    def close(self) -> None:
        try:
            if self._sftp is not None:
                self._sftp.close()
        finally:
            self.client.close()


# ---------------------------------------------------------------- чтение через API

def _retry(fn, attempts: int = 6, delay: float = 0.3):
    """Только что созданный файл какое-то время не читается — повторяем."""
    for i in range(attempts):
        try:
            return fn()
        except TrapError:
            if i == attempts - 1:
                raise
            time.sleep(delay)


def api_read_raw(api_l1, name: str, size: int) -> bytes:
    """Читает файл через /file/read по соединению с encoding='latin-1'.

    latin-1 переводит байты в символы один к одному. librouteros приводит типы
    («123» -> int, «yes» -> True): int обратим без потерь, а чтобы кусок не
    оказался «yes»/«no», хвост файла читается окном не короче 64 байт.
    """
    out = bytearray()
    off = 0
    while off < size:
        n = min(READ_CHUNK, size - off)
        start = off if (n >= 64 or size < 64) else size - 64
        length = n if start == off else size - start

        def once():
            rows = list(api_l1("/file/read", file=name, offset=start, **{"chunk-size": length}))
            return rows[0].get("data", "") if rows else ""

        value = _retry(once)
        if isinstance(value, bool):
            raise ValueError(f"{name}: неоднозначный ответ /file/read для крошечного файла")
        chunk = str(value).encode("latin-1")[off - start:]
        if len(chunk) != n:
            raise ValueError(f"{name}: получено {len(chunk)} байт вместо {n} на смещении {off}")
        out += chunk
        off += n
    return bytes(out)


def api_read_b64(api, name: str, size: int, chunk: int = 12288) -> bytes:
    """Читает файл кусками: роутер сам кодирует их в base64 (/execute as-string)."""
    out = bytearray()
    off = 0
    while off < size:
        n = min(chunk, size - off)
        script = (f':put [:convert ([/file/read file="{name}" offset={off} '
                  f'chunk-size={n} as-value]->"data") to=base64]')

        def once():
            rows = list(api("/execute", script=script, **{"as-string": True}))
            return rows[0].get("ret", "") if rows else ""

        text = re.sub(r"\s+", "", str(_retry(once)))
        try:
            data = base64.b64decode(text, validate=True)
        except binascii.Error as exc:
            raise ValueError(f"{name}: некорректный base64 на смещении {off}: {exc}") from exc
        if len(data) != n:
            raise ValueError(f"{name}: получено {len(data)} байт вместо {n} на смещении {off}")
        out += data
        off += n
    return bytes(out)


# ---------------------------------------------------------------- helpers

def _run(api, cmd: str, **kwargs) -> tuple:
    return tuple(api(cmd, **kwargs))


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:60]


def list_files(api, prefix: str = PREFIX) -> list[dict]:
    rows = []
    for f in api.path("file"):
        base = str(f.get("name", "")).rsplit("/", 1)[-1]
        if base.startswith(prefix) and f.get("type") != "directory":
            rows.append(f)
    return rows


def cleanup(api, prefix: str = PREFIX) -> None:
    ids = [str(f[".id"]) for f in list_files(api, prefix)]
    if ids:
        try:
            api.path("file").remove(*ids)
        except LibRouterosError as exc:
            log.warning("Не удалось удалить временные файлы: %s", exc)


def wait_files(api, expected: int, prefix: str = PREFIX, timeout: float = 90) -> list[dict]:
    """Ждём, пока появятся все файлы и их размер перестанет меняться."""
    deadline = time.monotonic() + timeout
    prev: dict[str, int] | None = None
    while time.monotonic() < deadline:
        files = list_files(api, prefix)
        sizes = {f["name"]: int(f.get("size") or 0) for f in files}
        if len(files) >= expected and all(sizes.values()) and sizes == prev:
            return files
        prev = sizes
        time.sleep(2)
    raise TimeoutError(f"Файлы не готовы: ожидалось {expected}, есть {list(prev or {})}")


def _want_cert(dev: Device, name: str) -> bool:
    if dev.certs == "all":
        return True
    if dev.certs in ("none", None, []):
        return False
    return name in dev.certs


def fetch_files(dev: Device, api, files: list[dict], known_hosts: Path) -> dict[str, bytes]:
    """Возвращает {базовое имя файла: содержимое} выбранным транспортом."""
    if dev.transport == "sftp":
        got = sftp_read_all(dev, known_hosts, [str(f["name"]) for f in files])
        return {p.rsplit("/", 1)[-1]: d for p, d in got.items()}

    out: dict[str, bytes] = {}
    api_l1 = open_api(dev, encoding="latin-1")
    try:
        for f in files:
            path, size = str(f["name"]), int(f.get("size") or 0)
            base = path.rsplit("/", 1)[-1]
            if base.endswith(BINARY_EXT) and dev.api_binary == "base64":
                out[base] = api_read_b64(api, path, size, dev.api_b64_chunk)
            else:
                out[base] = api_read_raw(api_l1, path, size)
            if len(out[base]) != size:
                raise ValueError(f"{base}: размер {len(out[base])} вместо {size}")
    finally:
        api_l1.close()
    return out


# ---------------------------------------------------------------- проверки

def required_policies(dev: Device) -> set[str]:
    need = {"read", "sensitive"}
    if dev.transport == "ssh":
        need |= {"ssh"}
        if not dev.config_only:
            need |= {"write", "ftp"}           # создание, чтение и удаление файлов
    else:
        need |= {"api", "write", "ftp"}        # экспорт идёт через файл
        if dev.transport == "sftp":
            need |= {"ssh"}
    if not dev.config_only:
        need |= {"policy", "test"}             # system backup save, сертификаты
    return need


def _parse_policies(text: str) -> set[str]:
    return {x.strip() for x in re.split(r"[;,\s]+", text) if x.strip() and not x.strip().startswith("!")}


def check_device(dev: Device, known_hosts: Path) -> dict:
    """Проверка доступа без экспорта: API-SSL / SSH, права группы, файловый транспорт."""
    info: dict = {"transport": dev.transport}
    if dev.transport == "ssh":
        ssh = SshSession(dev, known_hosts)
        try:
            info["identity"] = ssh.run(":put [/system identity get name]")
            info["version"] = ssh.run(":put [/system resource get version]")
            group = ssh.run(f":put [/user get [find name={ros_quote(dev.username)}] group]")
            policies = _parse_policies(ssh.run(
                f":put [/user group get [find name={ros_quote(group)}] policy]"))
            info["group"] = group
            info["missing_policies"] = sorted(required_policies(dev) - policies)
            if not dev.config_only:
                ssh.sftp.listdir(".")
            info["files"] = "SSH ok" + ("" if dev.config_only else ", SFTP ok")
        finally:
            ssh.close()
        return info

    api = open_api(dev)
    try:
        info["identity"] = str(next(iter(api.path("system", "identity")))["name"])
        info["version"] = str(next(iter(api.path("system", "resource")))["version"])
        group = next((str(u.get("group")) for u in api.path("user")
                      if u.get("name") == dev.username), None)
        policies: set[str] = set()
        for g in api.path("user", "group"):
            if g.get("name") == group:
                policies = _parse_policies(str(g.get("policy", "")))
        info["group"] = group
        info["missing_policies"] = sorted(required_policies(dev) - policies)
    finally:
        api.close()

    if dev.transport == "sftp":
        ssh = open_ssh(dev, known_hosts)
        try:
            ssh.open_sftp().listdir(".")
            info["files"] = "SFTP ok"
        finally:
            ssh.close()
    else:
        ok = parse_version(info["version"]) >= MIN_FILE_READ
        info["files"] = "API /file/read ok" if ok else "нужен RouterOS 7.13+ для /file/read"
        if not ok:
            info["missing_policies"].append("RouterOS>=7.13")
    return info


# ---------------------------------------------------------------- main

def _store_file(res: DeviceResult, base: str, data: bytes) -> None:
    if base.endswith(".rsc"):
        res.config = data
    elif base.endswith(".backup"):
        res.backup = data
    elif base.startswith(CERT_FILE):
        res.certs[base[len(CERT_FILE):]] = data


def _verify(res: DeviceResult, dev: Device, cert_files_expected: int) -> None:
    if not res.config:
        raise RuntimeError("Не получен экспорт конфигурации")
    if dev.want_backup and not res.backup:
        raise RuntimeError("Не получен system.backup")
    if len(res.certs) != cert_files_expected:
        raise RuntimeError(f"Получено {len(res.certs)} файлов сертификатов из {cert_files_expected}")


def _backup_via_ssh(dev: Device, passphrase: str, known_hosts: Path) -> DeviceResult:
    res = DeviceResult(dev.name, config_only=dev.config_only)
    ssh = SshSession(dev, known_hosts)
    files_created = False
    try:
        res.identity = ssh.run(":put [/system identity get name]")
        res.version = ssh.run(":put [/system resource get version]")
        log.info("%s: подключено по SSH (%s, RouterOS %s)", dev.name, res.identity, res.version)

        # 1. Конфиг — прямо из stdout, без файлов на роутере
        res.config = ssh.export_stdout()
        if dev.config_only:
            _verify(res, dev, 0)
            return res

        files_created = True
        ssh.cleanup()

        # 2. Бинарный backup
        if dev.want_backup:
            ssh.run(f"/system backup save name={SYS_FILE} password={ros_quote(passphrase)}")

        # 3. Сертификаты
        res.cert_index = sorted(ssh.cert_index(), key=lambda x: x["name"])
        to_export = [c for c in res.cert_index if c["private-key"] and _want_cert(dev, c["name"])]
        cert_type = "pkcs12" if dev.cert_format == "p12" else "pem"
        for c in to_export:
            ssh.run(f"/certificate export-certificate [find name={ros_quote(c['name'])}] "
                    f"type={cert_type} export-passphrase={ros_quote(passphrase)} "
                    f"file-name={CERT_FILE}{_safe_name(c['name'])}")

        per_cert = 1 if dev.cert_format == "p12" else 2
        expected = int(dev.want_backup) + per_cert * len(to_export)
        if expected:
            for path, size in ssh.wait_files(expected).items():
                data = ssh.read_file(path)
                if len(data) != size:
                    raise ValueError(f"{path}: прочитано {len(data)} байт вместо {size}")
                _store_file(res, path.rsplit("/", 1)[-1], data)
        _verify(res, dev, per_cert * len(to_export))
        return res
    finally:
        try:
            if files_created:
                ssh.cleanup()
        finally:
            ssh.close()


def backup_device(dev: Device, passphrase: str, known_hosts: Path) -> DeviceResult:
    if dev.transport == "ssh":
        return _backup_via_ssh(dev, passphrase, known_hosts)

    res = DeviceResult(dev.name, config_only=dev.config_only)
    api = open_api(dev)
    try:
        res.identity = str(next(iter(api.path("system", "identity")))["name"])
        res.version = str(next(iter(api.path("system", "resource")))["version"])
        log.info("%s: подключено (%s, RouterOS %s, транспорт %s)",
                 dev.name, res.identity, res.version, dev.transport)
        if dev.transport == "api" and parse_version(res.version) < MIN_FILE_READ:
            raise RuntimeError("transport: api требует RouterOS 7.13+ (/file/read)")

        cleanup(api)

        # 1. Текстовый экспорт с паролями и ключами
        _run(api, "/export", file=CFG_FILE, terse=True, **{"show-sensitive": True})

        # 2. Бинарный backup, зашифрованный паролем
        if dev.want_backup:
            _run(api, "/system/backup/save", name=SYS_FILE, password=passphrase)

        # 3. Сертификаты: индекс всех + выгрузка тех, у кого есть ключ
        to_export = []
        for c in (api.path("certificate") if dev.want_certs else ()):
            name = str(c.get("name"))
            res.cert_index.append({
                "name": name,
                "common-name": str(c.get("common-name", "")),
                "fingerprint": str(c.get("fingerprint", "")),
                "invalid-after": str(c.get("invalid-after", "")),
                "private-key": bool(c.get("private-key", False)),
            })
            if c.get("private-key") and _want_cert(dev, name):
                to_export.append(c)
        res.cert_index.sort(key=lambda x: x["name"])

        cert_type = "pkcs12" if dev.cert_format == "p12" else "pem"
        for c in to_export:
            _run(api, "/certificate/export-certificate",
                 numbers=str(c[".id"]), type=cert_type,
                 **{"export-passphrase": passphrase,
                    "file-name": CERT_FILE + _safe_name(str(c["name"]))})

        per_cert = 1 if dev.cert_format == "p12" else 2          # .p12 | .crt + .key
        expected = 1 + int(dev.want_backup) + per_cert * len(to_export)
        files = wait_files(api, expected)

        # 4. Забираем файлы выбранным транспортом
        for base, data in fetch_files(dev, api, files, known_hosts).items():
            _store_file(res, base, data)
        _verify(res, dev, per_cert * len(to_export))
        return res
    finally:
        try:
            cleanup(api)
        finally:
            api.close()


# ---------------------------------------------------------------- восстановление

def restore_config(dev: Device, known_hosts: Path, script: bytes) -> str:
    """Загружает .rsc по SFTP и выполняет /import. Всегда через SSH, при любом transport.

    /import применяет скрипт поверх текущей конфигурации: на «живом» роутере
    часть команд упадёт с «already have such entry». Рассчитано на сброшенное
    устройство или на частичные скрипты.
    """
    name = f"{PREFIX}restore.rsc"
    ssh = SshSession(dev, known_hosts)
    try:
        with ssh.sftp.open(name, "wb") as fh:
            fh.write(script)
        return ssh.run(f"/import file-name={name} verbose=no", timeout=600, check=False)
    finally:
        try:
            ssh.run(f'/file remove [find name="{name}"]', check=False)
        finally:
            ssh.close()
