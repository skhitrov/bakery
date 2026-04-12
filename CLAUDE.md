# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Online school diary (gradebook) for parents and teachers. Parents log in to view their child's weekly progress: theory/practice attendance, homework completion (4 items), test status, and teacher comments. Teachers can view all students. Built for a constrained server (1 CPU, 512 MB RAM, 10 GB HDD, 200–300 students).

## Commands

- **Install:** `pip install -e ".[dev]"`
- **Run:** `python3 -m uvicorn app.main:app --reload`
- **Seed demo data:** `python3 seed.py`
- **Lint:** `ruff check .`
- **Format:** `ruff format .`

No automated tests yet — validate with manual browser testing.

## Architecture

```
app/
  main.py        — FastAPI app, routes, startup
  database.py    — SQLite schema, connection helpers (get_db context manager)
  auth.py        — password hashing, session cookies (itsdangerous), login/logout
  config.py      — DB_PATH, SECRET_KEY, constants
  templates/     — Jinja2: base.html, login.html, diary.html
  static/        — style.css (vanilla CSS, mobile-first responsive)
seed.py          — populates DB with demo parents/teacher/students/weekly records
diary.db         — SQLite database (auto-created on first run, gitignored)
```

**Request flow:** all pages are server-rendered HTML (Jinja2). No SPA, no JavaScript framework. Auth is cookie-based sessions signed with itsdangerous.

**Data model:** `users` (parent/teacher/admin) → `students` (linked to parent) → `weekly_records` (one row per student per week, with boolean fields for attendance/hw/test and a text comment).

## Code Conventions

- `from __future__ import annotations` in modules using `X | None` syntax (required for Python < 3.10)
- Async route handlers by default
- All SQL uses parameterized queries (`?` placeholders)
- UI text in Russian
- CSS is mobile-first; tables get horizontal scroll on narrow screens via `.table-wrapper`

## Demo Accounts

- **Parent:** `petrov@mail.ru` / `pass123`
- **Teacher:** `admin@bulochka.ru` / `teacher123`
