"""Сброс пароля из консоли: временный пароль, восстановление admin."""
import time

import pytest

from mtb import auth
from mtb.db import Database


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "mtb.db")
    auth.ensure_admin(d)
    return d


def user(db, name):
    return db.one("SELECT * FROM users WHERE username=?", (name,))


def test_reset_gives_temp_password(db):
    auth.set_password(db, user(db, "admin")["id"], "old-password-1")
    auth.create_session(db, user(db, "admin")["id"], "127.0.0.1")
    action, temp = auth.reset_password(db, "admin")
    row = user(db, "admin")
    assert action == "reset"
    assert len(temp) >= auth.MIN_PASSWORD
    assert row["password_hash"] is not None, "учётка не должна оставаться без пароля"
    assert row["must_set_password"] == 1
    assert auth.authenticate(db, "admin", temp) is not None
    assert auth.authenticate(db, "admin", "old-password-1") is None
    assert db.one("SELECT COUNT(*) AS n FROM sessions")["n"] == 0


def test_reset_restores_admin_role(db):
    with db.tx() as c:
        c.execute("UPDATE users SET role='viewer'")
    action, _ = auth.reset_password(db, "admin")
    assert action == "promoted"
    assert user(db, "admin")["role"] == "admin"


def test_reset_recreates_deleted_admin(db):
    with db.tx() as c:
        c.execute("DELETE FROM users")
        c.execute("INSERT INTO users(username, password_hash, role, must_set_password, created_at) "
                  "VALUES('ivan', NULL, 'admin', 0, ?)", (time.time(),))
    action, temp = auth.reset_password(db, "admin")
    assert action == "created"
    assert user(db, "admin")["role"] == "admin"
    assert auth.authenticate(db, "admin", temp) is not None


def test_reset_other_user_keeps_role(db):
    with db.tx() as c:
        c.execute("INSERT INTO users(username, password_hash, role, must_set_password, created_at) "
                  "VALUES('ivan', NULL, 'viewer', 0, ?)", (time.time(),))
    action, _ = auth.reset_password(db, "ivan")
    assert action == "reset"
    assert user(db, "ivan")["role"] == "viewer"


def test_reset_unknown_user(db):
    assert auth.reset_password(db, "nobody") is None
    assert user(db, "nobody") is None
