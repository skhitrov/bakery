"""Цех (stream) management (teacher only)."""


def test_add_stream_increments_position(client, make_user, login, csrf, query):
    aid = make_user("teacher", "boss@test.ru")
    login("boss@test.ru")
    for name in ("Цех 1", "Цех 2"):
        r = client.post(
            "/admin/add-stream",
            data={"csrf_token": csrf(aid), "stream_name": name},
            follow_redirects=False,
        )
        assert r.status_code == 303
    rows = query("SELECT name, position FROM streams ORDER BY position")
    assert [(r["name"], r["position"]) for r in rows] == [("Цех 1", 1), ("Цех 2", 2)]


def test_delete_stream_unassigns_students_but_keeps_them(client, make_user, make_stream, make_student, login, csrf, query):
    aid = make_user("teacher", "boss@test.ru")
    sid = make_stream("Цех 1", 1)
    stud = make_student("Остаётся", stream_id=sid)
    login("boss@test.ru")
    r = client.post(
        "/admin/delete-stream",
        data={"csrf_token": csrf(aid), "stream_id": str(sid)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # Stream is gone...
    assert query("SELECT id FROM streams WHERE id = ?", (sid,)) == []
    # ...but the student is preserved, just unassigned.
    student = query("SELECT stream_id FROM students WHERE id = ?", (stud,))
    assert len(student) == 1
    assert student[0]["stream_id"] is None


def test_add_stream_bad_csrf_forbidden(client, make_user, login, query):
    make_user("teacher", "boss@test.ru")
    login("boss@test.ru")
    r = client.post(
        "/admin/add-stream",
        data={"csrf_token": "nope", "stream_name": "Хак"},
        follow_redirects=False,
    )
    assert r.status_code == 403
    assert query("SELECT id FROM streams WHERE name = ?", ("Хак",)) == []
