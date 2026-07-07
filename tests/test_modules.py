"""Module management (teacher only)."""


def test_add_module_increments_position(client, make_user, login, csrf, query):
    aid = make_user("teacher", "boss@test.ru")
    login("boss@test.ru")
    for name in ("Октябрь", "Ноябрь"):
        r = client.post(
            "/admin/add-module",
            data={"csrf_token": csrf(aid), "module_name": name},
            follow_redirects=False,
        )
        assert r.status_code == 303
    rows = query("SELECT name, position FROM modules ORDER BY position")
    assert [(r["name"], r["position"]) for r in rows] == [("Октябрь", 1), ("Ноябрь", 2)]


def test_delete_module_removes_records(client, make_user, make_module, make_student, login, csrf, query):
    aid = make_user("teacher", "boss@test.ru")
    mid = make_module("Сентябрь")
    stud = make_student("Ученик")
    from app.database import get_db
    with get_db() as conn:
        conn.execute(
            "INSERT INTO weekly_records (student_id, module_id, week_number) VALUES (?, ?, 1)",
            (stud, mid),
        )
    login("boss@test.ru")
    r = client.post(
        "/admin/delete-module",
        data={"csrf_token": csrf(aid), "module_id": str(mid)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert query("SELECT id FROM modules WHERE id = ?", (mid,)) == []
    assert query("SELECT id FROM weekly_records WHERE module_id = ?", (mid,)) == []


def test_add_module_bad_csrf_forbidden(client, make_user, login, query):
    make_user("teacher", "boss@test.ru")
    login("boss@test.ru")
    r = client.post(
        "/admin/add-module",
        data={"csrf_token": "nope", "module_name": "Хакер"},
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert query("SELECT id FROM modules WHERE name = ?", ("Хакер",)) == []
