"""mtb: бэкап конфигурации и сертификатов MikroTik RouterOS 7.

Настройки, устройства и пользователи — в веб-интерфейсе (хранятся в SQLite).

  mtb                        сервис: расписание + веб-интерфейс (= serve)
  mtb run [-d NAME]          один прогон и выход
  mtb check [-d NAME]        проверка доступа без экспорта
  mtb probe [-d NAME]        какой транспорт файлов работает (sftp / api / ssh)
  mtb fingerprint HOST[:PORT]
  mtb reset-password [USER]  пароль будет задан заново при следующем входе
  mtb update [--check] [-y]  обновить бинарник до нового релиза с GitHub
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from . import __version__, config

log = logging.getLogger("mtb")


class Context:
    def __init__(self, data_dir: str | None):
        self.boot = config.load_bootstrap(data_dir)
        self.db, self.box = config.open_storage(self.boot)

    def settings(self) -> config.Settings:
        return config.load(self.boot, self.db, self.box)

    def devices(self, only: list[str] | None) -> list[config.Device]:
        devs = self.settings().devices
        if only:
            unknown = set(only) - {d.name for d in devs}
            if unknown:
                raise SystemExit(f"Нет таких устройств: {', '.join(sorted(unknown))}")
            return [d for d in devs if d.name in only]
        return devs


# ---------------------------------------------------------------- команды

def cmd_serve(ctx: Context, web: bool = True) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    from .auth import ensure_admin
    from .runner import run_once

    ensure_admin(ctx.db)
    s = ctx.settings()
    sched = BlockingScheduler(timezone=ZoneInfo(s.timezone))

    def job():
        try:
            run_once(ctx.settings(), kind="scheduled", db=ctx.db)
        except Exception:  # noqa: BLE001 — планировщик не должен падать
            log.exception("Ошибка прогона по расписанию")

    def trigger(st: config.Settings):
        return CronTrigger.from_crontab(st.schedule, timezone=ZoneInfo(st.timezone))

    sched.add_job(job, trigger(s), id="backup", max_instances=1, coalesce=True, misfire_grace_time=3600)

    from datetime import datetime, timedelta
    from . import updater

    def update_job():
        try:
            v = config.read_settings(ctx.db, ctx.box)
            if v["update_check"]:
                st = updater.check(ctx.db, v["update_channel"])
                latest = (st.get("latest") or {}).get("version")
                if latest and updater.version_key(latest) > updater.version_key(__version__):
                    log.info("Доступна новая версия mtb: %s (текущая %s)", latest, __version__)
        except Exception:  # noqa: BLE001
            log.exception("Ошибка проверки обновлений")

    sched.add_job(update_job, "interval", hours=updater.CHECK_INTERVAL_HOURS, id="update-check",
                  next_run_time=datetime.now(ZoneInfo(s.timezone)) + timedelta(seconds=60),
                  max_instances=1, coalesce=True)

    def reschedule():
        st = ctx.settings()
        sched.reschedule_job("backup", trigger=trigger(st))
        log.info("Расписание обновлено: '%s' (%s)", st.schedule, st.timezone)

    if web:
        from .web import WebApp
        WebApp(ctx.boot, ctx.db, ctx.box, on_settings_changed=reschedule).start_background()

    log.info("mtb %s: расписание '%s' (%s), устройств: %d, бэкапы: %s, база: %s",
             __version__, s.schedule, s.timezone, len(s.devices), ctx.boot.backup_dir.resolve(),
             ctx.boot.db_path.resolve())
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        pass


def cmd_run(ctx: Context, only) -> bool:
    from .runner import run_once
    ctx.devices(only)
    return run_once(ctx.settings(), only=only, kind="scheduled" if not only else "manual",
                    db=ctx.db, user="cli").success


def cmd_check(ctx: Context, only) -> bool:
    from .mikrotik import check_device
    known_hosts = ctx.boot.data_dir / "known_hosts"
    all_ok = True
    for dev in ctx.devices(only):
        try:
            i = check_device(dev, known_hosts)
            miss = i["missing_policies"]
            all_ok &= not miss
            print(f"[{'OK' if not miss else 'ПРАВА'}] {dev.name}: {i['identity']}, RouterOS {i['version']}, "
                  f"группа {i['group']}, транспорт {i['transport']}: {i['files']}"
                  + (f", не хватает политик: {','.join(miss)}" if miss else ""))
        except Exception as exc:  # noqa: BLE001
            all_ok = False
            print(f"[ОШИБКА] {dev.name}: {type(exc).__name__}: {exc}")
    return all_ok


def cmd_probe(ctx: Context, only, use_sftp: bool) -> bool:
    from .probe import format_report, probe_device
    all_ok = True
    for dev in ctx.devices(only):
        print(f"Проверка {dev.name}… (временные файлы mtbk-probe-* будут удалены)", flush=True)
        rep = probe_device(dev, ctx.boot.data_dir / "known_hosts", use_sftp=use_sftp)
        all_ok &= not rep.error
        print(format_report(rep))
        print()
    return all_ok


def cmd_fingerprint(target: str) -> None:
    from .mikrotik import fetch_fingerprint
    host, _, port = target.rpartition(":") if target.count(":") == 1 else (target, "", "")
    info = fetch_fingerprint(host or target, int(port or 8729))
    print(f"fingerprint: {info['fingerprint']}")
    print(f"subject:     {info['subject']}")
    print(f"valid until: {info['not_after']}")
    print(f"key bits:    {info['key_bits']}")
    print()
    print(info["pem"], end="")


EXIT_UPDATE_AVAILABLE = 3


def _service_health(timeout: float = 3) -> dict | None:
    """Состояние запущенного сервиса через /healthz (идёт ли прогон, версия)."""
    import json
    import ssl
    import urllib.request
    host, _, port = os.environ.get("WEB_LISTEN", "0.0.0.0:8080").rpartition(":")
    host = host.strip("[]")
    host = "127.0.0.1" if host in ("", "0.0.0.0", "::") else host
    scheme = "https" if os.environ.get("WEB_TLS_CERT") else "http"
    ctx = ssl._create_unverified_context() if scheme == "https" else None   # свой же сервис на localhost
    try:
        with urllib.request.urlopen(f"{scheme}://{host}:{port or 8080}/healthz", timeout=timeout, context=ctx) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001 — сервис не запущен или недоступен
        return None


def cmd_update(args) -> int:
    import subprocess
    import time

    from . import updater

    logging.getLogger("mtb.update").setLevel(logging.ERROR)    # всё нужное команда печатает сама
    info = updater.install_info()
    if info["type"] != "binary":
        print(f"Обновление командой доступно для бинарника из install.sh, а это установка «{info['type']}».")
        print("Обновите так:\n" + updater.instructions(info, None)["commands"])
        return 1
    if not info.get("arch"):
        print(f"Архитектура {os.uname().machine} не поддерживается")
        return 1
    exe = Path(info["path"])
    is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    if not args.check and not (os.access(exe, os.W_OK) and os.access(exe.parent, os.W_OK)):
        print(f"Нет прав на запись в {exe.parent}. Запустите от root или от пользователя сервиса.")
        return 1

    # что ставить
    try:
        if args.version:
            target = updater.find_release(args.version)
        else:
            include_pre = True if args.pre else False if args.stable else updater.resolve_channel("auto")
            target = updater.pick_latest(updater.fetch_releases(), include_pre)
    except Exception as exc:  # noqa: BLE001
        print(f"Не удалось выбрать релиз: {exc}")
        return 1
    current = __version__
    if not target:
        print(f"Установлена v{current}. Подходящих релизов в {updater.REPO} нет.")
        return 0
    newer = updater.version_key(target["version"]) > updater.version_key(current)
    same = updater.version_key(target["version"]) == updater.version_key(current)
    label = " (пре-релиз)" if target["prerelease"] else ""
    if same and not args.version:
        print(f"Установлена последняя версия: v{current}.")
        return 0
    if not newer and not args.version:
        print(f"Установлена v{current}, последняя подходящая — v{target['version']}{label}. Обновлять нечего.")
        return 0
    print(f"Установлена: v{current}")
    print(f"{'Доступна' if newer else 'Выбрана'}:  v{target['version']}{label}  {target.get('url') or ''}")
    if target.get("notes") and not args.yes:
        notes = target["notes"].strip().splitlines()
        print("\n".join("  " + ln for ln in notes[:15]) + ("\n  …" if len(notes) > 15 else ""))
    if args.check:
        return EXIT_UPDATE_AVAILABLE if newer else 0
    if same:
        print("Эта версия уже установлена — будет переустановлена.")
    elif not newer:
        print("Внимание: это откат на более старую версию. Схема базы назад не откатывается.")

    if not args.yes:
        if not sys.stdin.isatty():
            print("Нет терминала для подтверждения — добавьте -y.")
            return 1
        if input(f"Обновить до v{target['version']}? [y/N] ").strip().lower() not in ("y", "yes", "д", "да"):
            print("Отменено.")
            return 1

    # не прерывать идущий бэкап
    health = _service_health()
    if health and health.get("running") and not args.force:
        print("Идёт бэкап — ждём его окончания (Ctrl+C — прервать, --force — не ждать)…", flush=True)
        deadline = time.monotonic() + 3600
        while (h := _service_health()) and h.get("running") and time.monotonic() < deadline:
            time.sleep(5)

    try:
        res = updater.install_binary(target, exe, info["arch"], progress=lambda m: print(m, flush=True))
    except Exception as exc:  # noqa: BLE001
        print(f"Обновление не выполнено: {exc}")
        return 1
    print(f"Бинарник обновлён: v{res['from']} → v{res['to']} ({exe}). Предыдущий — {exe}.prev")

    # перезапуск сервиса
    unit = os.environ.get("MTB_SERVICE", "mtb.service")
    has_systemd = Path("/run/systemd/system").is_dir() and shutil_which("systemctl")
    active = has_systemd and subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0
    if not active:
        print("Сервис не запущен через systemd — новая версия начнёт работать при следующем запуске.")
        return 0
    if not is_root:
        print(f"Перезапустите сервис: systemctl restart {unit}")
        return 0
    subprocess.run(["systemctl", "restart", unit], check=False)
    for _ in range(30):
        time.sleep(1)
        h = _service_health()
        if h and h.get("version") == res["to"]:
            print(f"Сервис перезапущен, работает v{h['version']}.")
            return 0
    print(f"Сервис перезапущен, но не ответил с новой версией. Проверьте: journalctl -u {unit} -e")
    print(f"Откат: mv {exe}.prev {exe} && systemctl restart {unit}")
    return 1


def shutil_which(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None


def cmd_reset_password(ctx: Context, username: str) -> None:
    from .auth import ensure_admin, reset_password
    ensure_admin(ctx.db)
    if not reset_password(ctx.db, username):
        raise SystemExit(f"Пользователь {username} не найден")
    ctx.db.audit("cli", "user_reset_password", username)
    print(f"Пароль {username} сброшен: при следующем входе в веб-интерфейс будет предложено задать новый.")


# ---------------------------------------------------------------- CLI

def _load_env_file(explicit: str | None) -> None:
    from dotenv import load_dotenv
    candidates = [explicit or os.environ.get("MTB_ENV") or ".env"]
    base = config.install_base()
    if not explicit and base:
        candidates.append(str(base / "mtb.env"))        # установка через install.sh
    for path in candidates:
        try:
            found = Path(path).is_file()
        except OSError:                     # текущий каталог недоступен пользователю сервиса
            found = False
        if found:
            load_dotenv(path, override=False)
            return
    if explicit:
        raise SystemExit(f"env-файл не найден: {explicit}")


def _drop_root(boot: config.Bootstrap) -> None:
    """Команда запущена от root — выполнить её от имени владельца данных.

    Иначе SQLite создаст рядом с базой файлы -wal/-shm от root, и сервис
    (пользователь mtb) не сможет писать в базу. Команда перезапускается
    отдельным процессом: бинарник PyInstaller распаковывает модули в каталог,
    доступный только root, поэтому сменить пользователя «на ходу» нельзя.
    """
    if not hasattr(os, "geteuid") or os.geteuid() != 0 or os.environ.get("MTB_AS_OWNER"):
        return
    data_dir = boot.data_dir.resolve()
    if not data_dir.is_dir():
        return
    st = data_dir.stat()
    if st.st_uid == 0:
        return
    import pwd
    import subprocess
    try:
        pw = pwd.getpwuid(st.st_uid)
        home, user = pw.pw_dir, pw.pw_name
    except KeyError:
        home, user = str(data_dir.parent), str(st.st_uid)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEIPASS"))}
    env.update({"MTB_AS_OWNER": "1", "HOME": home, "USER": user,
                "DATA_DIR": str(data_dir), "BACKUP_DIR": str(boot.backup_dir.resolve()),
                # новый экземпляр PyInstaller распакуется сам, а не возьмёт каталог родителя (он доступен только root)
                "PYINSTALLER_RESET_ENVIRONMENT": "1"})
    cmd = [sys.executable, *sys.argv[1:]] if getattr(sys, "frozen", False) else [sys.executable, "-m", "mtb", *sys.argv[1:]]
    log.debug("Команда выполняется от пользователя %s", user)
    try:
        rc = subprocess.run(cmd, user=st.st_uid, group=st.st_gid, extra_groups=[], env=env,
                            cwd=str(data_dir.parent)).returncode
    except KeyboardInterrupt:
        rc = 130
    sys.exit(rc)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", default=argparse.SUPPRESS,
                        help="папка с базой и ключом (по умолчанию $DATA_DIR или ./data)")
    common.add_argument("-e", "--env-file", default=argparse.SUPPRESS,
                        help="файл с переменными окружения (по умолчанию ./.env)")
    common.add_argument("--log-level", default=argparse.SUPPRESS, help="DEBUG, INFO, WARNING")

    ap = argparse.ArgumentParser(prog="mtb", parents=[common],
                                 description="Бэкап конфигурации и сертификатов MikroTik RouterOS 7")
    ap.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd", metavar="КОМАНДА")
    sub.add_parser("serve", aliases=["daemon"], parents=[common],
                   help="расписание и веб-интерфейс (по умолчанию)")
    sub.add_parser("scheduler", parents=[common], help="только расписание, без веб-интерфейса")
    for name, text in (("run", "один прогон и выход"), ("check", "проверка доступа без экспорта")):
        p = sub.add_parser(name, parents=[common], help=text)
        p.add_argument("-d", "--device", action="append", help="только это устройство (можно несколько)")
    pr = sub.add_parser("probe", parents=[common], help="проверить транспорты файлов на устройствах")
    pr.add_argument("-d", "--device", action="append")
    pr.add_argument("--no-sftp", action="store_true", help="не использовать SFTP как эталон")
    f = sub.add_parser("fingerprint", help="показать отпечаток TLS-сертификата api-ssl")
    f.add_argument("target", metavar="HOST[:PORT]")
    up = sub.add_parser("update", parents=[common], help="обновить бинарник до нового релиза с GitHub")
    up.add_argument("--check", action="store_true", help="только проверить (код выхода 3 — есть обновление)")
    up.add_argument("-y", "--yes", action="store_true", help="не спрашивать подтверждение")
    up.add_argument("--version", metavar="vX.Y.Z", help="конкретная версия, в том числе более старая")
    ch = up.add_mutually_exclusive_group()
    ch.add_argument("--pre", action="store_true", help="учитывать пре-релизы")
    ch.add_argument("--stable", action="store_true", help="только стабильные версии")
    up.add_argument("--force", action="store_true", help="не ждать окончания идущего бэкапа")
    rp = sub.add_parser("reset-password", parents=[common],
                        help="сбросить пароль: новый задаётся при следующем входе")
    rp.add_argument("username", nargs="?", default="admin")
    return ap


def main() -> None:
    args = build_parser().parse_args()
    cmd = {"daemon": "serve", None: "serve"}.get(args.cmd, args.cmd)

    logging.basicConfig(
        level=getattr(args, "log_level", None) or os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)

    if cmd == "fingerprint":
        cmd_fingerprint(args.target)
        return

    _load_env_file(getattr(args, "env_file", None))
    if cmd == "update":                     # от root: заменить бинарник и перезапустить сервис; базу не трогает
        sys.exit(cmd_update(args))
    _drop_root(config.load_bootstrap(getattr(args, "data_dir", None)))
    try:
        ctx = Context(getattr(args, "data_dir", None))
        only = getattr(args, "device", None)
        if cmd == "serve":
            cmd_serve(ctx)
        elif cmd == "scheduler":
            cmd_serve(ctx, web=False)
        elif cmd == "run":
            sys.exit(0 if cmd_run(ctx, only) else 1)
        elif cmd == "check":
            sys.exit(0 if cmd_check(ctx, only) else 1)
        elif cmd == "probe":
            sys.exit(0 if cmd_probe(ctx, only, not args.no_sftp) else 1)
        elif cmd == "reset-password":
            cmd_reset_password(ctx, args.username)
    except config.ConfigError as exc:
        raise SystemExit(f"Ошибка настроек: {exc}") from exc


if __name__ == "__main__":
    main()
