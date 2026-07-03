"""Shared pytest fixtures.

Every test runs in-process against a fresh temporary SQLite DB — the real
``diary.db`` is never touched. A fixed SECRET_KEY is set before any ``app.*``
import so token signing is deterministic and no ``.env`` is written.
"""

import os

# Must be set before app.config is imported (it reads SECRET_KEY at import time).
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def db_path(tmp_path, monkeypatch):
    """Point the app at a throwaway DB and initialise its schema."""
    import app.config as config
    import app.database as database

    p = tmp_path / "test.db"
    # get_connection() reads the module-global DB_PATH at call time.
    monkeypatch.setattr(database, "DB_PATH", p)
    monkeypatch.setattr(config, "DB_PATH", p)
    database.init_db()
    return p


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The login rate limiter is in-process global state; reset it per test."""
    import app.auth as auth
    auth._login_attempts.clear()
    yield
    auth._login_attempts.clear()


@pytest.fixture()
def client(db_path):
    from app.main import app
    with TestClient(app) as c:
        yield c


# --------------------------------------------------------------------------
# Data factories (write straight to the temp DB, reusing app helpers)
# --------------------------------------------------------------------------

@pytest.fixture()
def query(db_path):
    """Run a read query against the temp DB and return all rows."""
    from app.database import get_db

    def _query(sql, params=()):
        with get_db() as conn:
            return conn.execute(sql, params).fetchall()

    return _query


@pytest.fixture()
def make_user(db_path):
    from app.auth import hash_password
    from app.database import get_db

    def _make(role, email, password="pass123", full_name=None):
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (email, password, role, full_name) VALUES (?, ?, ?, ?)",
                (email, hash_password(password), role, full_name or email),
            )
            return conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]

    return _make


@pytest.fixture()
def make_stream(db_path):
    from app.database import get_db

    def _make(name, position=0):
        with get_db() as conn:
            conn.execute("INSERT INTO streams (name, position) VALUES (?, ?)", (name, position))
            return conn.execute("SELECT id FROM streams WHERE name = ?", (name,)).fetchone()[0]

    return _make


@pytest.fixture()
def make_module(db_path):
    from app.database import get_db

    def _make(name, position=1):
        with get_db() as conn:
            conn.execute("INSERT INTO modules (name, position) VALUES (?, ?)", (name, position))
            return conn.execute("SELECT id FROM modules WHERE name = ?", (name,)).fetchone()[0]

    return _make


@pytest.fixture()
def make_student(db_path):
    from app.database import get_db

    def _make(full_name, parent_id=None, stream_id=None):
        with get_db() as conn:
            conn.execute(
                "INSERT INTO students (full_name, parent_id, stream_id) VALUES (?, ?, ?)",
                (full_name, parent_id, stream_id),
            )
            return conn.execute(
                "SELECT id FROM students WHERE full_name = ? ORDER BY id DESC", (full_name,)
            ).fetchone()[0]

    return _make


@pytest.fixture()
def csrf():
    """Mint a valid CSRF token bound to a user id (SECRET_KEY is fixed)."""
    from app.auth import generate_csrf_token
    return generate_csrf_token


@pytest.fixture()
def login(client):
    """Log the shared TestClient in; the session cookie persists on `client`."""
    def _login(email, password="pass123"):
        return client.post(
            "/login",
            data={"email": email, "password": password},
            follow_redirects=False,
        )
    return _login
