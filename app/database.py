import sqlite3
from contextlib import contextmanager

from app.config import DB_PATH

SCHEMA = """\
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT    NOT NULL UNIQUE,
    password    TEXT    NOT NULL,
    role        TEXT    NOT NULL CHECK (role IN ('parent', 'teacher', 'admin')),
    full_name   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS streams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name   TEXT    NOT NULL,
    parent_id   INTEGER REFERENCES users(id),
    stream_id   INTEGER REFERENCES streams(id)
);

CREATE TABLE IF NOT EXISTS modules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS weekly_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      INTEGER NOT NULL REFERENCES students(id),
    module_id       INTEGER NOT NULL REFERENCES modules(id),
    week_number     INTEGER NOT NULL,
    theory          INTEGER NOT NULL DEFAULT 0,
    practice        INTEGER NOT NULL DEFAULT 0,
    hw1             INTEGER NOT NULL DEFAULT 0,
    hw2             INTEGER NOT NULL DEFAULT 0,
    hw3             INTEGER NOT NULL DEFAULT 0,
    hw4             INTEGER NOT NULL DEFAULT 0,
    test            INTEGER NOT NULL DEFAULT 0,
    trial_exam      TEXT    NOT NULL DEFAULT '',
    comment         TEXT    NOT NULL DEFAULT '',
    updated_at      REAL    NOT NULL DEFAULT 0,
    UNIQUE(student_id, module_id, week_number)
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(SCHEMA)
        # Migrate: add updated_at if missing (existing DBs)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(weekly_records)").fetchall()]
        if "updated_at" not in cols:
            conn.execute("ALTER TABLE weekly_records ADD COLUMN updated_at REAL NOT NULL DEFAULT 0")
        # Migrate: add stream_id to students if missing (existing DBs)
        scols = [r[1] for r in conn.execute("PRAGMA table_info(students)").fetchall()]
        if "stream_id" not in scols:
            conn.execute("ALTER TABLE students ADD COLUMN stream_id INTEGER REFERENCES streams(id)")
