"""Команды из консоли находят базу сервиса и не заводят новую."""
import os
import subprocess
import sys
from pathlib import Path

from mtb.main import parse_unit_env


def test_parse_unit_env_legacy_layout():
    out = ("Environment=BACKUP_DIR=/var/lib/mtb/backups DATA_DIR=/var/lib/mtb/data WEB_LISTEN=0.0.0.0:8080\n"
           "EnvironmentFiles=/etc/mtb/mtb.env (ignore_errors=yes)\n")
    env, env_file = parse_unit_env(out)
    assert env["DATA_DIR"] == "/var/lib/mtb/data"
    assert env["BACKUP_DIR"] == "/var/lib/mtb/backups"
    assert env_file == "/etc/mtb/mtb.env"


def test_parse_unit_env_quoted_and_empty():
    env, env_file = parse_unit_env('Environment="DATA_DIR=/srv/my data"\nEnvironmentFiles=\n')
    assert env["DATA_DIR"] == "/srv/my data"
    assert env_file is None
    assert parse_unit_env("") == ({}, None)


def test_reset_password_needs_existing_db(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("DATA_DIR", "BACKUP_DIR")}
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    r = subprocess.run([sys.executable, "-m", "mtb", "--data-dir", str(tmp_path / "data"), "reset-password"],
                       capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode != 0
    assert "База не найдена" in r.stderr
    assert not (tmp_path / "data").exists(), "пустая база не должна создаваться"
