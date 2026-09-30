"""mtb: бэкап конфигурации и сертификатов MikroTik RouterOS 7.

Настройки, устройства и пользователи — в веб-интерфейсе (хранятся в SQLite).

  mtb                        сервис: расписание + веб-интерфейс (= serve)
  mtb run [-d NAME]          один прогон и выход
  mtb check [-d NAME]        проверка доступа без экспорта
  mtb probe [-d NAME]        какой транспорт файлов работает (sftp / api / ssh)
  mtb fingerprint HOST[:PORT]
  mtb reset-password [USER]  пароль будет задан заново при следующем входе
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
    path = explicit or os.environ.get("MTB_ENV") or ".env"
    if Path(path).is_file():
        load_dotenv(path, override=False)
    elif explicit:
        raise SystemExit(f"env-файл не найден: {path}")


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
