"""Teacher-only curator (admin) account management: add, delete, CSRF, role guards.

Only the ``teacher`` role may manage curators. Admins/curators and parents are
rejected. Deletion is scoped to ``role='admin'`` so it can never touch other accounts.
"""


def test_teacher_can_add_curator(client, make_user, login, csrf, query):
    tid = make_user("teacher", "t@test.ru")
    login("t@test.ru")
    r = client.post(
        "/admin/add-curator",
        data={
            "csrf_token": csrf(tid),
            "full_name": "Новый Куратор",
            "email": "curator2@test.ru",
            "password": "pass123",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    rows = query("SELECT role FROM users WHERE email = ?", ("curator2@test.ru",))
    assert len(rows) == 1
    assert rows[0]["role"] == "admin"


def test_teacher_added_curator_can_login(client, make_user, login, csrf):
    tid = make_user("teacher", "t@test.ru")
    login("t@test.ru")
    r = client.post(
        "/admin/add-curator",
        data={
            "csrf_token": csrf(tid),
            "full_name": "Второй Куратор",
            "email": "curator3@test.ru",
            "password": "strongpass",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    from app.auth import authenticate

    assert authenticate("curator3@test.ru", "strongpass") is not None


def test_add_curator_duplicate_email_rejected(client, make_user, login, csrf, query):
    tid = make_user("teacher", "t@test.ru")
    make_user("parent", "taken@mail.ru")
    login("t@test.ru")
    r = client.post(
        "/admin/add-curator",
        data={
            "csrf_token": csrf(tid),
            "full_name": "Дубликат",
            "email": "taken@mail.ru",
            "password": "pass123",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/admin?error=curator_exists"
    # The pre-existing account keeps its original role; no admin was created.
    rows = query("SELECT role FROM users WHERE email = ?", ("taken@mail.ru",))
    assert len(rows) == 1
    assert rows[0]["role"] == "parent"


def test_add_curator_rejects_short_password(client, make_user, login, csrf, query):
    tid = make_user("teacher", "t@test.ru")
    login("t@test.ru")
    r = client.post(
        "/admin/add-curator",
        data={
            "csrf_token": csrf(tid),
            "full_name": "Слабый Пароль",
            "email": "weak@test.ru",
            "password": "123",  # < MIN_PASSWORD_LENGTH
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert query("SELECT id FROM users WHERE email = ?", ("weak@test.ru",)) == []


def test_add_curator_bad_csrf_forbidden(client, make_user, login, query):
    make_user("teacher", "t@test.ru")
    login("t@test.ru")
    r = client.post(
        "/admin/add-curator",
        data={
            "csrf_token": "bogus",
            "full_name": "NoCSRF",
            "email": "nocsrf@test.ru",
            "password": "pass123",
        },
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert query("SELECT id FROM users WHERE email = ?", ("nocsrf@test.ru",)) == []


def test_admin_cannot_add_curator(client, make_user, login, csrf, query):
    aid = make_user("admin", "boss@test.ru")
    login("boss@test.ru")
    r = client.post(
        "/admin/add-curator",
        data={
            "csrf_token": csrf(aid),
            "full_name": "Не Создан",
            "email": "byadmin@test.ru",
            "password": "pass123",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    assert query("SELECT id FROM users WHERE email = ?", ("byadmin@test.ru",)) == []


def test_parent_cannot_add_curator(client, make_user, login, csrf, query):
    pid = make_user("parent", "p@mail.ru")
    login("p@mail.ru")
    r = client.post(
        "/admin/add-curator",
        data={
            "csrf_token": csrf(pid),
            "full_name": "Escalation",
            "email": "escalate@test.ru",
            "password": "pass123",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    assert query("SELECT id FROM users WHERE email = ?", ("escalate@test.ru",)) == []


def test_teacher_can_delete_curator(client, make_user, login, csrf, query):
    tid = make_user("teacher", "t@test.ru")
    cid = make_user("admin", "gone@test.ru")
    login("t@test.ru")
    r = client.post(
        "/admin/delete-curator",
        data={"csrf_token": csrf(tid), "user_id": str(cid)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert query("SELECT id FROM users WHERE id = ?", (cid,)) == []


def test_admin_cannot_delete_curator(client, make_user, login, csrf, query):
    aid = make_user("admin", "boss@test.ru")
    other = make_user("admin", "keep@test.ru")
    login("boss@test.ru")
    r = client.post(
        "/admin/delete-curator",
        data={"csrf_token": csrf(aid), "user_id": str(other)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    assert len(query("SELECT id FROM users WHERE id = ?", (other,))) == 1


def test_delete_curator_only_targets_admins(client, make_user, login, csrf, query):
    tid = make_user("teacher", "t@test.ru")
    parent = make_user("parent", "p@mail.ru")
    login("t@test.ru")
    r = client.post(
        "/admin/delete-curator",
        data={"csrf_token": csrf(tid), "user_id": str(parent)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # The role='admin' guard means a non-curator is untouched.
    assert len(query("SELECT id FROM users WHERE id = ?", (parent,))) == 1


def test_delete_curator_bad_csrf_forbidden(client, make_user, login, query):
    make_user("teacher", "t@test.ru")
    cid = make_user("admin", "keep@test.ru")
    login("t@test.ru")
    r = client.post(
        "/admin/delete-curator",
        data={"csrf_token": "bogus", "user_id": str(cid)},
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert len(query("SELECT id FROM users WHERE id = ?", (cid,))) == 1
