"""Teacher/admin student roster management (add, delete, change-password, CSRF)."""


def test_add_student_creates_parent_and_assigns_stream(client, make_user, make_stream, login, csrf, query):
    tid = make_user("teacher", "t@test.ru")
    sid = make_stream("Поток 1", 1)
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
    sid = make_stream("Поток 1", 1)
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
