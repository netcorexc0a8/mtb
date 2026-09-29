"""mtb probe: проверка, каким способом можно забирать файлы с роутера.

На роутере создаются временные файлы mtbk-probe-* (экспорт, backup, сертификат
в PKCS#12 и PEM) со случайным паролем. Каждый файл читается:
  - по SFTP — эталон (если SSH доступен);
  - через API /file/read сырыми байтами (raw);
  - через API с base64 на стороне роутера, куски разного размера.
Дополнительно сравнивается вывод `/export` в stdout SSH (транспорт ssh) с
экспортом в файл. Для устройств с transport: ssh проверяется только SSH.
Результаты сравниваются по SHA-256 с эталоном и проверяются на валидность
(PKCS#12 и PEM расшифровываются тестовым паролем). В конце — рекомендация
для настроек устройства. Временные файлы удаляются.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import Device
from .mikrotik import (
    MIN_FILE_READ, SshSession, api_read_b64, api_read_raw, cleanup, open_api, parse_version,
    sftp_read_all, wait_files,
)
from .storage import normalize_export

PROBE_PREFIX = "mtbk-probe-"
B64_CHUNKS = (3072, 12288, 24576)


@dataclass
class Attempt:
    status: str            # OK | DIFF | BAD | ERR
    seconds: float = 0.0
    detail: str = ""
    sha: str = ""


@dataclass
class FileReport:
    name: str
    size: int
    binary: bool
    reference: str = ""    # sha256 эталона (SFTP)
    valid_ref: str = ""
    attempts: dict[str, Attempt] = field(default_factory=dict)


@dataclass
class ProbeReport:
    device: str
    version: str = ""
    file_read: bool = False
    sftp: str = ""
    files: list[FileReport] = field(default_factory=list)
    error: str = ""
    recommendation: dict = field(default_factory=dict)
    note: str = ""
    mode: str = "api"      # api | ssh
    ssh_stdout: str = ""   # сравнение /export из stdout SSH с экспортом в файл


def _validate(name: str, data: bytes, pw: str) -> str:
    """Пустая строка — файл валиден, иначе описание проблемы."""
    try:
        if name.endswith(".rsc"):
            text = data.decode("utf-8", errors="replace")
            return "" if "/" in text and text.lstrip().startswith("#") else "не похоже на экспорт"
        if name.endswith(".crt"):
            from cryptography import x509
            x509.load_pem_x509_certificate(data)
        elif name.endswith(".key"):
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            load_pem_private_key(data, pw.encode())
        elif name.endswith(".p12"):
            from cryptography.hazmat.primitives.serialization import pkcs12
            pkcs12.load_key_and_certificates(data, pw.encode())
        return ""
    except Exception as exc:  # noqa: BLE001 — нужна только диагностика
        return f"{type(exc).__name__}: {exc}"[:80]


def _judge(fr: FileReport, data: bytes, pw: str) -> Attempt:
    if len(data) != fr.size:
        return Attempt("BAD", detail=f"{len(data)} байт вместо {fr.size}")
    sha = hashlib.sha256(data).hexdigest()
    if fr.reference:
        if sha == fr.reference:
            return Attempt("OK", sha=sha)
        return Attempt("DIFF", detail="не совпадает с SFTP", sha=sha)
    problem = _validate(fr.name, data, pw)
    return Attempt("BAD", detail=problem, sha=sha) if problem else Attempt("OK", sha=sha)


def _cross_check(fr: FileReport) -> None:
    """Без эталона: успешные способы должны дать одинаковые байты."""
    good = [a for a in fr.attempts.values() if a.status == "OK"]
    if len({a.sha for a in good}) > 1:
        for a in good:
            a.status, a.detail = "DIFF", "способы чтения дали разные данные"


def _compare_stdout(dev: Device, known_hosts: Path, file_export: bytes) -> str:
    """/export show-sensitive terse в stdout SSH против того же экспорта в файл."""
    ssh = SshSession(dev, known_hosts)
    try:
        t0 = time.monotonic()
        out = ssh.export_stdout()
        secs = time.monotonic() - t0
    finally:
        ssh.close()
    a, b = normalize_export(out), normalize_export(file_export)
    if a == b:
        return f"OK {secs:.1f}s"
    la, lb = a.splitlines(), b.splitlines()
    first = next((i for i, (x, y) in enumerate(zip(la, lb)) if x != y), min(len(la), len(lb)))
    return f"DIFF: строк {len(la)} против {len(lb)}, первое расхождение в строке {first + 1}"


def _probe_ssh(dev: Device, known_hosts: Path) -> ProbeReport:
    """transport: ssh — stdout-экспорт против файла, плюс чтение backup по SFTP."""
    rep = ProbeReport(dev.name, sftp="-", mode="ssh")
    pw = secrets.token_urlsafe(18)
    ssh = None
    try:
        ssh = SshSession(dev, known_hosts)
        rep.version = ssh.run(":put [/system resource get version]")
        ssh.cleanup(PROBE_PREFIX)
        ssh.run(f"/export show-sensitive terse file={PROBE_PREFIX}cfg")
        if not dev.config_only:
            ssh.run(f'/system backup save name={PROBE_PREFIX}sys password="{pw}"')
        sizes = ssh.wait_files(1 + int(not dev.config_only), prefix=PROBE_PREFIX)
        for path, size in sorted(sizes.items()):
            data = ssh.read_file(path)
            base = path.rsplit("/", 1)[-1]
            fr = FileReport(base, size, base.endswith(".backup"))
            fr.attempts["sftp"] = Attempt("OK" if len(data) == size else "BAD",
                                          detail="" if len(data) == size else f"{len(data)} байт")
            rep.files.append(fr)
            if base.endswith(".rsc"):
                rep.ssh_stdout = _compare_stdout(dev, known_hosts, data)
        rep.sftp = "ok"
        if rep.ssh_stdout.startswith("OK") and all(f.attempts["sftp"].status == "OK" for f in rep.files):
            rep.recommendation = {"transport": "ssh"}
            if dev.config_only:
                rep.recommendation["config_only"] = True
        return rep
    except Exception as exc:  # noqa: BLE001
        rep.error = f"{type(exc).__name__}: {exc}"
        return rep
    finally:
        if ssh is not None:
            ssh.cleanup(PROBE_PREFIX)
            ssh.close()


def probe_device(dev: Device, known_hosts: Path, use_sftp: bool = True) -> ProbeReport:
    if dev.transport == "ssh":
        return _probe_ssh(dev, known_hosts)
    rep = ProbeReport(dev.name)
    pw = secrets.token_urlsafe(18)
    api = api_l1 = None
    try:
        api = open_api(dev)
        rep.version = str(next(iter(api.path("system", "resource")))["version"])
        rep.file_read = parse_version(rep.version) >= MIN_FILE_READ
        cleanup(api, PROBE_PREFIX)

        tuple(api("/export", file=f"{PROBE_PREFIX}cfg", terse=True, **{"show-sensitive": True}))
        tuple(api("/system/backup/save", name=f"{PROBE_PREFIX}sys", password=pw))
        expected = 2
        cert = next((c for c in api.path("certificate") if c.get("private-key")), None)
        if cert is not None:
            for kind, fname in (("pkcs12", "p12"), ("pem", "pem")):
                tuple(api("/certificate/export-certificate", numbers=str(cert[".id"]), type=kind,
                          **{"export-passphrase": pw, "file-name": f"{PROBE_PREFIX}{fname}"}))
            expected += 3                                   # .p12 + .crt + .key
        else:
            rep.note = "нет сертификатов с приватным ключом — .p12/PEM не проверялись"
        files = wait_files(api, expected, prefix=PROBE_PREFIX)
        paths = {str(f["name"]): int(f.get("size") or 0) for f in files}

        for path, size in sorted(paths.items()):
            base = path.rsplit("/", 1)[-1]
            rep.files.append(FileReport(base, size, base.endswith((".backup", ".p12"))))

        # Эталон по SFTP
        if use_sftp:
            try:
                ref = sftp_read_all(dev, known_hosts, list(paths))
                rep.sftp = "ok"
                for fr, path in zip(rep.files, sorted(paths)):
                    fr.reference = hashlib.sha256(ref[path]).hexdigest()
                    fr.valid_ref = _validate(fr.name, ref[path], pw)
                    if fr.name.endswith(".rsc"):
                        try:
                            rep.ssh_stdout = _compare_stdout(dev, known_hosts, ref[path])
                        except Exception as exc:  # noqa: BLE001
                            rep.ssh_stdout = f"ERR: {type(exc).__name__}: {exc}"[:100]
            except Exception as exc:  # noqa: BLE001
                rep.sftp = f"{type(exc).__name__}: {exc}"[:100]
        else:
            rep.sftp = "пропущен"

        if not rep.file_read:
            rep.error = f"RouterOS {rep.version}: /file/read появился в 7.13, режим api недоступен"
            return rep

        api_l1 = open_api(dev, encoding="latin-1")
        methods = {"raw": lambda p, s: api_read_raw(api_l1, p, s)}
        for ch in B64_CHUNKS:
            methods[f"b64/{ch}"] = lambda p, s, ch=ch: api_read_b64(api, p, s, ch)

        for fr, path in zip(rep.files, sorted(paths)):
            for mname, fn in methods.items():
                t0 = time.monotonic()
                try:
                    data = fn(path, fr.size)
                    att = _judge(fr, data, pw)
                except Exception as exc:  # noqa: BLE001
                    att = Attempt("ERR", detail=f"{type(exc).__name__}: {exc}"[:80])
                att.seconds = time.monotonic() - t0
                fr.attempts[mname] = att
            if not fr.reference:
                _cross_check(fr)

        if not any(fr.reference for fr in rep.files):
            extra = ("без SFTP-эталона .backup проверен только по размеру и совпадению "
                     "результатов разных способов")
            rep.note = f"{rep.note}; {extra}" if rep.note else extra

        rep.recommendation = _recommend(rep)
        return rep
    except Exception as exc:  # noqa: BLE001
        rep.error = f"{type(exc).__name__}: {exc}"
        return rep
    finally:
        if api is not None:
            try:
                cleanup(api, PROBE_PREFIX)
            except Exception:  # noqa: BLE001
                pass
            api.close()
        if api_l1 is not None:
            api_l1.close()


def _recommend(rep: ProbeReport) -> dict:
    text = [f for f in rep.files if not f.binary]
    binary = [f for f in rep.files if f.binary]
    ok = lambda f, m: f.attempts.get(m) and f.attempts[m].status == "OK"  # noqa: E731

    if not text or not all(ok(f, "raw") for f in text):
        return {"transport": "sftp"} if rep.sftp == "ok" else {}
    if all(ok(f, "raw") for f in binary):
        return {"transport": "api", "api_binary": "raw"}
    good_chunks = [ch for ch in B64_CHUNKS if all(ok(f, f"b64/{ch}") for f in binary)]
    if good_chunks:
        return {"transport": "api", "api_binary": "base64", "api_b64_chunk": max(good_chunks)}
    skip = {"transport": "api", "api_binary": "skip", "cert_format": "pem"}
    if rep.sftp == "ok":
        rep.note = ("бинарные файлы через API не читаются; без SSH можно работать в режиме "
                    "transport: api, api_binary: skip, cert_format: pem (без system.backup)")
        return {"transport": "sftp"}
    return skip


def format_report(rep: ProbeReport) -> str:
    lines = [f"== {rep.device} (RouterOS {rep.version or '?'})"]
    if rep.mode == "ssh":
        lines.append(f"   transport: ssh   SFTP: {rep.sftp or '-'}")
    else:
        lines.append(f"   /file/read: {'есть' if rep.file_read else 'нет'}   SFTP: {rep.sftp or '-'}")
    if rep.ssh_stdout:
        lines.append(f"   /export через stdout SSH (transport: ssh): {rep.ssh_stdout}")
    if rep.files:
        methods = list(rep.files[0].attempts) or []
        head = f"   {'файл':<24}{'размер':>9}  " + "".join(f"{m:<14}" for m in methods)
        lines.append(head)
        for fr in rep.files:
            cells = []
            for m in methods:
                a = fr.attempts.get(m)
                cells.append(f"{(a.status + f' {a.seconds:.1f}s') if a else '-':<14}")
            lines.append(f"   {fr.name:<24}{fr.size:>9}  " + "".join(cells))
        details = [(fr.name, m, a.detail) for fr in rep.files for m, a in fr.attempts.items()
                   if a.status != "OK" and a.detail]
        for name, m, d in details:
            lines.append(f"   ! {name} [{m}]: {d}")
        for fr in rep.files:
            if fr.valid_ref:
                lines.append(f"   i {fr.name}: эталон по SFTP не разобрался ({fr.valid_ref}) — "
                             "для .p12 это бывает из-за устаревших алгоритмов, на результат не влияет")
    if rep.note:
        lines.append(f"   i {rep.note}")
    if rep.error:
        lines.append(f"   ОШИБКА: {rep.error}")
    if rep.recommendation:
        rec = ", ".join(f"{k}: {v}" for k, v in rep.recommendation.items())
        lines.append(f"   Рекомендация для настроек устройства → {rec}")
    elif not rep.error:
        lines.append("   Рекомендации нет: ни SFTP, ни API не прошли проверку")
    return "\n".join(lines)
