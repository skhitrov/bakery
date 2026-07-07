"""Teacher/admin student roster management (add, delete, change-password, CSRF)."""


def test_add_student_creates_parent_and_assigns_stream(client, make_user, make_stream, login, csrf, query):
    tid = make_user("teacher", "t@test.ru")
    sid = make_stream("Цех 1", 1)
    login("t@test.ru")
    r = client.post(
        "/admin/add-student",
        data={
            "csrf_token": csrf(tid),
            "full_name": "Иванов Петя",
            "parent_name": "Иванов Пётр",
            "parent_email": "ivanov@mail.ru",
            "parent_password": "pass123",
            "stream_id": str(sid),
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    students = query("SELECT parent_id, stream_id FROM students WHERE full_name = ?", ("Иванов Петя",))
    assert len(students) == 1
    assert students[0]["stream_id"] == sid
    assert students[0]["parent_id"] is not None
    parent = query("SELECT role FROM users WHERE email = ?", ("ivanov@mail.ru",))
    assert parent[0]["role"] == "parent"


def test_add_student_reuses_existing_parent(client, make_user, login, csrf, query):
    tid = make_user("teacher", "t@test.ru")
    existing_parent = make_user("parent", "shared@mail.ru")
    login("t@test.ru")
    r = client.post(
        "/admin/add-student",
        data={
            "csrf_token": csrf(tid),
            "full_name": "Второй Ребёнок",
            "parent_name": "Общий Родитель",
            "parent_email": "shared@mail.ru",
            "parent_password": "pass123",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    # No duplicate user; student linked to the existing parent.
    users = query("SELECT id FROM users WHERE email = ?", ("shared@mail.ru",))
    assert len(users) == 1
    student = query("SELECT parent_id FROM students WHERE full_name = ?", ("Второй Ребёнок",))
    assert student[0]["parent_id"] == existing_parent


def test_add_student_rejects_short_parent_password(client, make_user, login, csrf, query):
    tid = make_user("teacher", "t@test.ru")
    login("t@test.ru")
    r = client.post(
        "/admin/add-student",
        data={
            "csrf_token": csrf(tid),
            "full_name": "Не Создан",
            "parent_email": "p@mail.ru",
            "parent_password": "123",  # < MIN_PASSWORD_LENGTH
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert query("SELECT id FROM students WHERE full_name = ?", ("Не Создан",)) == []
    assert query("SELECT id FROM users WHERE email = ?", ("p@mail.ru",)) == []


def test_add_student_without_parent(client, make_user, make_stream, login, csrf, query):
    tid = make_user("teacher", "t@test.ru")
    sid = make_stream("Цех 1", 1)
    login("t@test.ru")
    r = client.post(
        "/admin/add-student",
        data={"csrf_token": csrf(tid), "full_name": "Без Родителя", "stream_id": str(sid)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    student = query("SELECT parent_id, stream_id FROM students WHERE full_name = ?", ("Без Родителя",))
    assert student[0]["parent_id"] is None
    assert student[0]["stream_id"] == sid


def test_delete_student_removes_records(client, make_user, make_module, make_student, login, csrf, query):
    tid = make_user("teacher", "t@test.ru")
    mid = make_module("Сентябрь")
    stud = make_student("Удаляемый")
    from app.database import get_db
    with get_db() as conn:
        conn.execute(
            "INSERT INTO weekly_records (student_id, module_id, week_number) VALUES (?, ?, 1)",
            (stud, mid),
        )
    login("t@test.ru")
    r = client.post(
        "/admin/delete-student",
        data={"csrf_token": csrf(tid), "student_id": str(stud)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert query("SELECT id FROM students WHERE id = ?", (stud,)) == []
    assert query("SELECT id FROM weekly_records WHERE student_id = ?", (stud,)) == []


def test_change_password_updates_parent(client, make_user, login, csrf, query):
    tid = make_user("teacher", "t@test.ru")
    pid = make_user("parent", "p@mail.ru", "oldpass")
    login("t@test.ru")
    r = client.post(
        "/admin/change-password",
        data={"csrf_token": csrf(tid), "user_id": str(pid), "new_password": "brandnew1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    from app.auth import authenticate
    assert authenticate("p@mail.ru", "brandnew1") is not None
    assert authenticate("p@mail.ru", "oldpass") is None


def test_change_password_cannot_target_staff(client, make_user, login, csrf):
    tid = make_user("teacher", "t@test.ru")
    aid = make_user("admin", "boss@test.ru", "bosspass")
    login("t@test.ru")
    client.post(
        "/admin/change-password",
        data={"csrf_token": csrf(tid), "user_id": str(aid), "new_password": "hijacked1"},
        follow_redirects=False,
    )
    from app.auth import authenticate
    # role='parent' guard means the admin password is unchanged.
    assert authenticate("boss@test.ru", "bosspass") is not None
    assert authenticate("boss@test.ru", "hijacked1") is None


def test_moving_student_between_cohorts_keeps_all_records(
    client, make_user, make_stream, make_module, make_student, login, query
):
    """Moving a student to another Цех must carry ALL their data with them.

    weekly_records are keyed by student_id (no stream_id column), so a move is just
    `UPDATE students SET stream_id = ?` and every record follows automatically —
    nothing to migrate. This test encodes that invariant.
    """
    make_user("admin", "curator@test.ru")  # only the curator renders the grid
    ceh1 = make_stream("Цех 1", 1)
    ceh2 = make_stream("Цех 2", 2)
    mid = make_module("Сентябрь")
    stud = make_student("Переводимый Ученик", stream_id=ceh1)

    from app.database import get_db

    # Give the student a fully-populated record while in Цех 1.
    with get_db() as conn:
        conn.execute(
            "INSERT INTO weekly_records "
            "(student_id, module_id, week_number, theory, practice, hw1, comment, updated_at) "
            "VALUES (?, ?, 1, 1, 1, 1, 'важный комментарий', 123.0)",
            (stud, mid),
        )

    # --- The move: student_id is untouched, only stream_id changes. ---
    with get_db() as conn:
        conn.execute("UPDATE students SET stream_id = ? WHERE id = ?", (ceh2, stud))

    # 1. Records are intact, still linked to the same student.
    recs = query(
        "SELECT week_number, theory, practice, hw1, comment FROM weekly_records WHERE student_id = ?",
        (stud,),
    )
    assert len(recs) == 1
    assert recs[0]["theory"] == 1 and recs[0]["practice"] == 1 and recs[0]["hw1"] == 1
    assert recs[0]["comment"] == "важный комментарий"

    login("curator@test.ru")
    # 2. The grid now shows the student AND their data under Цех 2...
    r2 = client.get("/admin", params={"stream": ceh2})
    assert "Переводимый Ученик" in r2.text
    assert "важный комментарий" in r2.text  # the record moved with the student

    # 3. ...and no longer under Цех 1.
    r1 = client.get("/admin", params={"stream": ceh1})
    assert "Переводимый Ученик" not in r1.text


def test_change_stream_moves_student_and_keeps_records(
    client, make_user, make_stream, make_module, make_student, login, csrf, query
):
    tid = make_user("teacher", "t@test.ru")
    ceh1 = make_stream("Цех 1", 1)
    ceh2 = make_stream("Цех 2", 2)
    mid = make_module("Сентябрь")
    stud = make_student("Переводимый", stream_id=ceh1)
    from app.database import get_db

    with get_db() as conn:
        conn.execute(
            "INSERT INTO weekly_records "
            "(student_id, module_id, week_number, theory, comment, updated_at) "
            "VALUES (?, ?, 1, 1, 'держись', 5.0)",
            (stud, mid),
        )
    login("t@test.ru")
    r = client.post(
        "/admin/change-stream",
        data={"csrf_token": csrf(tid), "student_id": str(stud), "stream_id": str(ceh2)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert query("SELECT stream_id FROM students WHERE id = ?", (stud,))[0]["stream_id"] == ceh2
    # Records followed the student (keyed by student_id, not stream).
    recs = query("SELECT theory, comment FROM weekly_records WHERE student_id = ?", (stud,))
    assert len(recs) == 1 and recs[0]["theory"] == 1 and recs[0]["comment"] == "держись"


def test_change_stream_bad_csrf_forbidden(client, make_user, make_stream, make_student, login, query):
    make_user("teacher", "t@test.ru")
    ceh1 = make_stream("Цех 1", 1)
    ceh2 = make_stream("Цех 2", 2)
    stud = make_student("Остаётся", stream_id=ceh1)
    login("t@test.ru")
    r = client.post(
        "/admin/change-stream",
        data={"csrf_token": "bad", "student_id": str(stud), "stream_id": str(ceh2)},
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert query("SELECT stream_id FROM students WHERE id = ?", (stud,))[0]["stream_id"] == ceh1


def test_change_stream_rejects_nonexistent_stream(
    client, make_user, make_stream, make_student, login, csrf, query
):
    tid = make_user("teacher", "t@test.ru")
    ceh1 = make_stream("Цех 1", 1)
    stud = make_student("Остаётся", stream_id=ceh1)
    login("t@test.ru")
    r = client.post(
        "/admin/change-stream",
        data={"csrf_token": csrf(tid), "student_id": str(stud), "stream_id": "99999"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # Bogus target stream is ignored — the student stays put.
    assert query("SELECT stream_id FROM students WHERE id = ?", (stud,))[0]["stream_id"] == ceh1


def test_admin_cannot_change_stream(
    client, make_user, make_stream, make_student, login, csrf, query
):
    aid = make_user("admin", "boss@test.ru")
    ceh1 = make_stream("Цех 1", 1)
    ceh2 = make_stream("Цех 2", 2)
    stud = make_student("Остаётся", stream_id=ceh1)
    login("boss@test.ru")
    r = client.post(
        "/admin/change-stream",
        data={"csrf_token": csrf(aid), "student_id": str(stud), "stream_id": str(ceh2)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    # Teacher-only guard: the curator cannot move students.
    assert query("SELECT stream_id FROM students WHERE id = ?", (stud,))[0]["stream_id"] == ceh1


def test_teacher_roster_renders_stream_change_control(
    client, make_user, make_stream, make_student, login
):
    make_user("teacher", "t@test.ru")
    ceh1 = make_stream("Цех 1", 1)
    make_stream("Цех 2", 2)
    make_student("Ученик Один", stream_id=ceh1)
    login("t@test.ru")
    r = client.get("/admin")
    assert r.status_code == 200
    # The editable «Цех» cell renders with both cohorts as options.
    assert 'action="/admin/change-stream"' in r.text
    assert "Цех 1" in r.text and "Цех 2" in r.text
    assert "Сменить" in r.text


def test_add_student_form_is_part_of_roster_table(client, make_user, make_stream, login):
    make_user("teacher", "t@test.ru")
    make_stream("Цех 1", 1)
    login("t@test.ru")
    r = client.get("/admin")
    assert r.status_code == 200
    # The add-student <form> is a shell; its controls live in a table row and are
    # bound to it via form= so they line up with the roster columns.
    assert 'id="add-student-form"' in r.text
    assert 'form="add-student-form"' in r.text
    assert 'class="add-student-row"' in r.text
    assert 'name="full_name"' in r.text


def test_add_student_bad_csrf_forbidden(client, make_user, login, query):
    make_user("teacher", "t@test.ru")
    login("t@test.ru")
    r = client.post(
        "/admin/add-student",
        data={"csrf_token": "bogus", "full_name": "NoCSRF"},
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert query("SELECT id FROM students WHERE full_name = ?", ("NoCSRF",)) == []
