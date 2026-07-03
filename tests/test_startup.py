"""The lifespan handler must initialise the schema on app startup."""

import sqlite3

from fastapi.testclient import TestClient


def _tables(path):
    conn = sqlite3.connect(str(path))
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_init_db_runs_on_startup(tmp_path, monkeypatch):
    """Entering the app (lifespan) must create the schema — without any manual init_db()."""
    import app.config as config
    import app.database as database

    p = tmp_path / "startup.db"
    monkeypatch.setattr(database, "DB_PATH", p)
    monkeypatch.setattr(config, "DB_PATH", p)

    # Nothing has initialised the DB yet.
    assert not p.exists()

    from app.main import app
    with TestClient(app):  # context-enter triggers the lifespan -> init_db()
        pass

    assert {"users", "students", "modules", "weekly_records", "streams"} <= _tables(p)
