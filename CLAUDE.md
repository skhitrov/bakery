# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Online school diary (gradebook) for parents and teachers, project «ПЕКАРНЯ» (Bakery). Parents log in to view their child's progress; a curator (admin) fills in the grid. Progress is tracked per **module** (a named period, e.g. "Сентябрь"), each split into 4 weeks. For every student-week the diary records theory/practice attendance, four homework items (hw1–hw4), a test flag, a free-text trial-exam field, and a teacher comment. Built for a constrained server (1 CPU, 512 MB RAM, 10 GB HDD, 200–300 students).

## Commands

- **Install:** `pip install -e ".[dev]"` (Python ≥ 3.11)
- **Run:** `python3 -m uvicorn app.main:app --reload`
- **Seed demo data:** `python3 seed.py` (no-op if the DB already has users)
- **Lint:** `ruff check .`
- **Format:** `ruff format .`

No automated tests yet — validate with manual browser testing. (`pytest`/`httpx` are installed as dev deps but there is no `tests/` dir.)

## Architecture

```
app/
  main.py        — FastAPI app, all routes, startup (init_db)
  database.py    — SQLite schema, get_connection/get_db context manager, init_db + lightweight migration
  auth.py        — scrypt hashing, itsdangerous sessions + CSRF, in-memory login rate limiting
  config.py      — DB_PATH, SECRET_KEY loading, constants (MIN_PASSWORD_LENGTH, SESSION_COOKIE)
  templates/     — Jinja2: base.html, login.html, diary.html (parent/read view), admin.html (curator grid + roster)
  static/        — style.css (vanilla CSS, mobile-first responsive)
seed.py          — demo admin/teacher/parents/students + one module of weekly records
diary.db         — SQLite database (auto-created on first run, gitignored)
```

**Request flow:** all pages are server-rendered HTML (Jinja2). No SPA, no JS framework. Auth is a cookie-based session (`session`) signed with itsdangerous (httponly, samesite=strict, 1-day max-age).

**Roles & permissions** (three roles — this is the key model to get right):
- **parent** — sees only their own children's diary at `/diary` (read-only).
- **teacher** — sees the `/admin` roster; can add/delete students, create parent accounts, and reset parent passwords. **Cannot** edit weekly records or manage modules.
- **admin** (curator) — everything a teacher can do, **plus** editing the weekly-records grid (`/admin/save`) and adding/deleting modules. The admin grid is only rendered for `role == "admin"`.

Route guards live inline at the top of each handler in `main.py` (check `get_current_user` + role, else redirect to `/login`). `/` redirects parents to `/diary` and staff to `/admin`.

**Data model:** `users` (parent/teacher/admin) → `students` (each linked to a `parent_id`) and `modules` (name + `position` ordering). `weekly_records` holds one row per `(student_id, module_id, week_number)` — enforced by a UNIQUE constraint — with integer-boolean fields (theory, practice, hw1–hw4, test), text `trial_exam` and `comment`, and a `updated_at` REAL timestamp. `WEEKS_PER_MODULE = 4` (constant in `main.py`).

## Security & Concurrency (don't regress these)

- **Passwords:** scrypt, stored as `scrypt:salt:hash`. Legacy `salt:sha256` hashes are still verified and transparently re-hashed to scrypt on successful login (`_rehash_if_legacy`).
- **CSRF:** every admin POST carries a `csrf_token` (itsdangerous, bound to the user id) validated via `_check_csrf`; failure returns 403. When adding a new admin form, include the token and validate it.
- **Rate limiting:** in-memory per-IP on `/login` — 5 attempts / 5-min window, then a 60 s block (`check_rate_limit`/`record_failed_login`). State is in-process, so it resets on restart and isn't shared across workers.
- **Optimistic concurrency:** `/admin/save` compares each cell's submitted `updated_at` against the DB; if the DB is newer it aborts the whole save and redirects to `/admin?error=conflict` (shown as a banner). Records are upserted via `ON CONFLICT(...) DO UPDATE`.

## Configuration

- `SECRET_KEY` is read from the `SECRET_KEY` env var, else from a `BASE_DIR/.env` file, else generated and **appended to `.env`** on first run (`config._load_secret_key`). Keep `.env` out of git and stable across restarts (rotating it invalidates all sessions).
- `DB_PATH` is `BASE_DIR/diary.db`. SQLite runs in WAL mode with `foreign_keys=ON`.

## Deployment

- **CI/CD:** `.github/workflows/deploy.yml` runs on push to `main` — SSHes to the server (`vars.SERVER_IP`, `secrets.SERVER_SSH_KEY`), `scp`s the app to `/opt/diary`, recreates `.venv` if broken, `pip install -e .`, and `systemctl restart diary`. It deliberately preserves `.venv`, `diary.db`, `backups/`, and `.env` on the server.
- **Backups:** `backup.sh` does a hot-safe `sqlite3 .backup` into `/opt/diary/backups`, pruning files older than 2 days. Driven by `diary-backup.service` + `diary-backup.timer` (systemd) at 08:00 and 20:00 daily.

## Code Conventions

- `from __future__ import annotations` in modules using `X | None` syntax.
- Async route handlers by default.
- All SQL uses parameterized queries (`?` placeholders).
- UI text is in Russian.
- CSS is mobile-first; wide tables get horizontal scroll on narrow screens via `.table-wrapper`.

## Demo Accounts (after `seed.py`)

- **Admin / curator:** `curator@test.ru` / `pass123` — the only account that can edit the grid.
- **Teacher:** `admin@bulochka.ru` / `teacher123`
- **Parents:** `petrov@mail.ru`, `sidorova@mail.ru`, `kuznetsov@mail.ru` — all `pass123`.
