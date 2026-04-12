import time

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config import SESSION_COOKIE, MIN_PASSWORD_LENGTH
from app.database import init_db, get_db
from app.auth import (
    authenticate,
    create_session_cookie,
    get_current_user,
    hash_password,
    generate_csrf_token,
    validate_csrf_token,
    check_rate_limit,
    record_failed_login,
)

WEEKS_PER_MODULE = 4

app = FastAPI(title="Учебный журнал | проект «ПЕКАРНЯ»")

_base = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_base / "templates"))
app.mount("/static", StaticFiles(directory=str(_base / "static")), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _csrf_error() -> HTMLResponse:
    return HTMLResponse("CSRF token invalid", status_code=403)


def _check_csrf(request: Request, form: dict, user: dict) -> bool:
    return validate_csrf_token(form.get("csrf_token"), user["id"])


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user["role"] == "parent":
        return RedirectResponse("/diary", status_code=303)
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/add-student")
async def admin_add_student(request: Request):
    user = get_current_user(request)
    if not user or user["role"] not in ("admin", "teacher"):
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    if not _check_csrf(request, form, user):
        return _csrf_error()

    full_name = (form.get("full_name") or "").strip()
    if not full_name:
        return RedirectResponse("/admin", status_code=303)

    parent_email = (form.get("parent_email") or "").strip()
    parent_password = form.get("parent_password") or ""
    parent_name = (form.get("parent_name") or "").strip()

    with get_db() as conn:
        parent_id = None
        if parent_email and parent_password:
            if len(parent_password) < MIN_PASSWORD_LENGTH:
                return RedirectResponse("/admin", status_code=303)
            existing = conn.execute(
                "SELECT id FROM users WHERE email = ?", (parent_email,)
            ).fetchone()
            if existing:
                parent_id = existing["id"]
            else:
                conn.execute(
                    "INSERT INTO users (email, password, role, full_name) VALUES (?, ?, ?, ?)",
                    (parent_email, hash_password(parent_password), "parent", parent_name or full_name),
                )
                parent_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO students (full_name, parent_id) VALUES (?, ?)", (full_name, parent_id)
        )
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/change-password")
async def admin_change_password(request: Request):
    user = get_current_user(request)
    if not user or user["role"] not in ("admin", "teacher"):
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    if not _check_csrf(request, form, user):
        return _csrf_error()

    user_id = int(form.get("user_id") or 0)
    new_password = (form.get("new_password") or "").strip()
    if new_password and len(new_password) >= MIN_PASSWORD_LENGTH:
        with get_db() as conn:
            conn.execute(
                "UPDATE users SET password = ? WHERE id = ? AND role = 'parent'",
                (hash_password(new_password), user_id),
            )
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/delete-student")
async def admin_delete_student(request: Request):
    user = get_current_user(request)
    if not user or user["role"] not in ("admin", "teacher"):
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    if not _check_csrf(request, form, user):
        return _csrf_error()

    student_id = int(form.get("student_id") or 0)
    with get_db() as conn:
        conn.execute("DELETE FROM weekly_records WHERE student_id = ?", (student_id,))
        conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/add-module")
async def admin_add_module(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    if not _check_csrf(request, form, user):
        return _csrf_error()

    module_name = (form.get("module_name") or "").strip()
    if module_name:
        with get_db() as conn:
            max_pos = conn.execute(
                "SELECT COALESCE(MAX(position), 0) FROM modules"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO modules (name, position) VALUES (?, ?)",
                (module_name, max_pos + 1),
            )
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/delete-module")
async def admin_delete_module(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    if not _check_csrf(request, form, user):
        return _csrf_error()

    module_id = int(form.get("module_id") or 0)
    with get_db() as conn:
        conn.execute("DELETE FROM weekly_records WHERE module_id = ?", (module_id,))
        conn.execute("DELETE FROM modules WHERE id = ?", (module_id,))
    return RedirectResponse("/admin", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": error}
    )


@app.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    ip = _client_ip(request)
    if not check_rate_limit(ip):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Слишком много попыток. Подождите минуту."},
            status_code=429,
        )

    user = authenticate(email, password)
    if not user:
        record_failed_login(ip)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный email или пароль"},
            status_code=401,
        )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        create_session_cookie(user["id"]),
        httponly=True,
        samesite="strict",
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/diary", response_class=HTMLResponse)
async def diary_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    with get_db() as conn:
        modules = conn.execute(
            "SELECT * FROM modules ORDER BY position"
        ).fetchall()
        modules = [dict(m) for m in modules]

        if user["role"] == "parent":
            students = conn.execute(
                "SELECT * FROM students WHERE parent_id = ? ORDER BY full_name",
                (user["id"],),
            ).fetchall()
        else:
            students = conn.execute(
                "SELECT * FROM students ORDER BY full_name"
            ).fetchall()

        records = conn.execute(
            "SELECT * FROM weekly_records ORDER BY module_id, week_number"
        ).fetchall()
        # Build {student_id: {module_id: {week_number: record}}}
        rec_map: dict = {}
        for r in records:
            r = dict(r)
            rec_map.setdefault(r["student_id"], {}).setdefault(
                r["module_id"], {}
            )[r["week_number"]] = r

        result = []
        for student in students:
            s = dict(student)
            student_modules = []
            for mod in modules:
                weeks = []
                for wn in range(1, WEEKS_PER_MODULE + 1):
                    rec = rec_map.get(s["id"], {}).get(mod["id"], {}).get(wn, {})
                    week_data = dict(rec) if rec else {}
                    week_data["week_number"] = wn
                    weeks.append(week_data)
                student_modules.append({"module": mod, "weeks": weeks})
            result.append({"student": s, "modules": student_modules})

    return templates.TemplateResponse(
        "diary.html",
        {"request": request, "user": user, "data": result},
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, error: str = ""):
    user = get_current_user(request)
    if not user or user["role"] not in ("teacher", "admin"):
        return RedirectResponse("/login", status_code=303)

    csrf_token = generate_csrf_token(user["id"])
    conflict_error = error == "conflict"

    with get_db() as conn:
        students = conn.execute(
            "SELECT s.*, u.full_name AS parent_name, u.email AS parent_email "
            "FROM students s LEFT JOIN users u ON s.parent_id = u.id "
            "ORDER BY s.full_name"
        ).fetchall()
        students = [dict(s) for s in students]

        modules = conn.execute(
            "SELECT * FROM modules ORDER BY position"
        ).fetchall()
        modules = [dict(m) for m in modules]

        module_data = []
        if user["role"] == "admin":
            records = conn.execute(
                "SELECT * FROM weekly_records ORDER BY module_id, week_number, student_id"
            ).fetchall()
            rec_map: dict = {}
            for r in records:
                r = dict(r)
                rec_map.setdefault(r["module_id"], {}).setdefault(
                    r["week_number"], {}
                )[r["student_id"]] = r

            for mod in modules:
                weeks = []
                for wn in range(1, WEEKS_PER_MODULE + 1):
                    rows = []
                    for s in students:
                        rec = rec_map.get(mod["id"], {}).get(wn, {}).get(s["id"], {})
                        rows.append({"student": s, "record": rec})
                    weeks.append({"week_number": wn, "rows": rows})
                module_data.append({"module": mod, "weeks": weeks})

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": user,
            "module_data": module_data,
            "modules": modules,
            "students": students,
            "csrf_token": csrf_token,
            "conflict_error": conflict_error,
        },
    )


@app.post("/admin/save")
async def admin_save(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/login", status_code=303)

    form = await request.form()
    if not _check_csrf(request, form, user):
        return _csrf_error()

    now = time.time()

    with get_db() as conn:
        # Load current updated_at values for conflict detection
        existing = {}
        for r in conn.execute(
            "SELECT student_id, module_id, week_number, updated_at FROM weekly_records"
        ).fetchall():
            existing[(r["student_id"], r["module_id"], r["week_number"])] = r["updated_at"]

        modules = conn.execute("SELECT id FROM modules").fetchall()
        students = conn.execute("SELECT id FROM students").fetchall()

        # Check for conflicts first
        for mod in modules:
            mid = mod["id"]
            for wn in range(1, WEEKS_PER_MODULE + 1):
                for s in students:
                    sid = s["id"]
                    prefix = f"m{mid}_w{wn}_s{sid}_"
                    form_ts = form.get(f"{prefix}updated_at", "0")
                    try:
                        form_ts = float(form_ts)
                    except (ValueError, TypeError):
                        form_ts = 0.0
                    db_ts = existing.get((sid, mid, wn), 0.0)
                    if db_ts > form_ts:
                        return RedirectResponse("/admin?error=conflict", status_code=303)

        # No conflicts — save all records
        for mod in modules:
            mid = mod["id"]
            for wn in range(1, WEEKS_PER_MODULE + 1):
                for s in students:
                    sid = s["id"]
                    prefix = f"m{mid}_w{wn}_s{sid}_"
                    theory = 1 if form.get(f"{prefix}theory") else 0
                    practice = 1 if form.get(f"{prefix}practice") else 0
                    test = 1 if form.get(f"{prefix}test") else 0
                    hw1 = 1 if form.get(f"{prefix}hw1") else 0
                    hw2 = 1 if form.get(f"{prefix}hw2") else 0
                    hw3 = 1 if form.get(f"{prefix}hw3") else 0
                    hw4 = 1 if form.get(f"{prefix}hw4") else 0
                    trial_exam = form.get(f"{prefix}trial_exam", "").strip()
                    comment = form.get(f"{prefix}comment", "").strip()

                    conn.execute(
                        "INSERT INTO weekly_records "
                        "(student_id, module_id, week_number, theory, practice, hw1, hw2, hw3, hw4, test, trial_exam, comment, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(student_id, module_id, week_number) DO UPDATE SET "
                        "theory=excluded.theory, practice=excluded.practice, "
                        "hw1=excluded.hw1, hw2=excluded.hw2, hw3=excluded.hw3, hw4=excluded.hw4, "
                        "test=excluded.test, trial_exam=excluded.trial_exam, comment=excluded.comment, "
                        "updated_at=excluded.updated_at",
                        (sid, mid, wn, theory, practice, hw1, hw2, hw3, hw4, test, trial_exam, comment, now),
                    )

    return RedirectResponse("/admin", status_code=303)
