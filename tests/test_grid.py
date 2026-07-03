"""Curator grid: Поток filtering, saving, save-isolation, optimistic concurrency."""

import pytest


@pytest.fixture()
def grid_setup(make_user, make_module, make_stream, make_student):
    """An admin, one module, two streams each with one student."""
    admin_id = make_user("admin", "boss@test.ru")
    mid = make_module("Сентябрь")
    s1 = make_stream("Поток 1", 1)
    s2 = make_stream("Поток 2", 2)
    a = make_student("Первый Ученик", stream_id=s1)
    b = make_student("Второй Ученик", stream_id=s2)
    return {"admin_id": admin_id, "mid": mid, "s1": s1, "s2": s2, "a": a, "b": b}


# --------------------------- filtering (GET) ---------------------------

def test_no_selection_hides_grid_shows_hint(client, grid_setup, login):
    login("boss@test.ru")
    r = client.get("/admin")
    assert r.status_code == 200
    assert "admin-table" not in r.text
    assert "Выберите поток" in r.text


def test_stream_filter_shows_only_that_cohort(client, grid_setup, login):
    login("boss@test.ru")
    r = client.get("/admin", params={"stream": grid_setup["s1"]})
    assert "Первый Ученик" in r.text
    assert "Второй Ученик" not in r.text
    # 1 student x 1 module x 4 weeks
    assert r.text.count('class="student-cell"') == 4


def test_all_streams_shows_everyone(client, grid_setup, login):
    login("boss@test.ru")
    r = client.get("/admin", params={"stream": "all"})
    assert "Первый Ученик" in r.text
    assert "Второй Ученик" in r.text
    assert r.text.count('class="student-cell"') == 8


# --------------------------- saving (POST) ---------------------------

def test_save_writes_cells(client, grid_setup, login, csrf, query):
    g = grid_setup
    p = f"m{g['mid']}_w1_s{g['a']}_"
    login("boss@test.ru")
    r = client.post(
        "/admin/save",
        data={"csrf_token": csrf(g["admin_id"]), "stream": str(g["s1"]), f"{p}theory": "on"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/admin?stream={g['s1']}"
    rec = query(
        "SELECT theory, updated_at FROM weekly_records WHERE student_id=? AND module_id=? AND week_number=1",
        (g["a"], g["mid"]),
    )
    assert rec[0]["theory"] == 1
    assert rec[0]["updated_at"] > 0


def test_save_is_isolated_between_streams(client, grid_setup, login, csrf, query):
    """Saving Поток 1 must not alter Поток 2's records — the critical invariant."""
    g = grid_setup
    from app.database import get_db
    # Give Поток 2's student a known, complete record.
    with get_db() as conn:
        conn.execute(
            "INSERT INTO weekly_records "
            "(student_id, module_id, week_number, theory, practice, hw1, comment, updated_at) "
            "VALUES (?, ?, 1, 1, 1, 1, 'keep me', 0)",
            (g["b"], g["mid"]),
        )
    before = query(
        "SELECT theory, practice, hw1, comment FROM weekly_records WHERE student_id=?",
        (g["b"],),
    )
    # Save Поток 1 (submits only Поток 1's cells).
    p = f"m{g['mid']}_w1_s{g['a']}_"
    login("boss@test.ru")
    r = client.post(
        "/admin/save",
        data={"csrf_token": csrf(g["admin_id"]), "stream": str(g["s1"]), f"{p}theory": "on"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    after = query(
        "SELECT theory, practice, hw1, comment FROM weekly_records WHERE student_id=?",
        (g["b"],),
    )
    assert [dict(x) for x in before] == [dict(x) for x in after]


def test_save_conflict_aborts_without_writing(client, grid_setup, login, csrf, query):
    g = grid_setup
    from app.database import get_db
    # Existing record is newer than what the form will claim.
    with get_db() as conn:
        conn.execute(
            "INSERT INTO weekly_records (student_id, module_id, week_number, theory, updated_at) "
            "VALUES (?, ?, 1, 0, 9999999999)",
            (g["a"], g["mid"]),
        )
    p = f"m{g['mid']}_w1_s{g['a']}_"
    login("boss@test.ru")
    r = client.post(
        "/admin/save",
        data={
            "csrf_token": csrf(g["admin_id"]),
            "stream": str(g["s1"]),
            f"{p}updated_at": "1.0",   # stale
            f"{p}theory": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error=conflict" in r.headers["location"]
    # The stale write was rejected: theory stays 0.
    rec = query(
        "SELECT theory FROM weekly_records WHERE student_id=? AND module_id=? AND week_number=1",
        (g["a"], g["mid"]),
    )
    assert rec[0]["theory"] == 0


def test_save_bad_csrf_forbidden(client, grid_setup, login):
    g = grid_setup
    login("boss@test.ru")
    r = client.post(
        "/admin/save",
        data={"csrf_token": "bad", "stream": str(g["s1"])},
        follow_redirects=False,
    )
    assert r.status_code == 403
