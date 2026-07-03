"""Schema init + the lightweight stream_id migration."""

import sqlite3

import pytest


def test_init_db_idempotent(db_path):
    from app.database import init_db
    # db_path fixture already ran it once; extra runs must not error.
    init_db()
    init_db()
    cols = [r[1] for r in sqlite3.connect(str(db_path)).execute("PRAGMA table_info(students)")]
    assert "stream_id" in cols


def test_migration_adds_streams_and_stream_id_to_legacy_db(tmp_path, monkeypatch):
    import app.config as config
    import app.database as database

    p = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(p))
    conn.executescript(
        """
        CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, password TEXT, role TEXT, full_name TEXT);
        CREATE TABLE students (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, parent_id INTEGER);
        CREATE TABLE modules (id INTEGER PRIMARY KEY, name TEXT, position INTEGER);
        """
    )
    conn.execute("INSERT INTO students (full_name) VALUES ('Старый Ученик')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(database, "DB_PATH", p)
    monkeypatch.setattr(config, "DB_PATH", p)
    database.init_db()

    conn = sqlite3.connect(str(p))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(students)")]
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    row = conn.execute("SELECT full_name, stream_id FROM students").fetchone()
    conn.close()

    assert "stream_id" in cols
    assert "streams" in tables
    # legacy row preserved, unassigned
    assert row == ("Старый Ученик", None)


def test_role_check_constraint(db_path):
    from app.database import get_db
    with pytest.raises(sqlite3.IntegrityError):
        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (email, password, role, full_name) VALUES (?, ?, ?, ?)",
                ("x@test.ru", "h", "superuser", "X"),
            )
