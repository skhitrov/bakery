"""Parent read-only diary visibility."""

import pytest


def test_parent_sees_only_own_child(client, make_user, make_student, login):
    p1 = make_user("parent", "p1@test.ru")
    p2 = make_user("parent", "p2@test.ru")
    make_student("Ребёнок Первый", parent_id=p1)
    make_student("Ребёнок Второй", parent_id=p2)
    login("p1@test.ru")
    r = client.get("/diary")
    assert r.status_code == 200
    assert "Ребёнок Первый" in r.text
    assert "Ребёнок Второй" not in r.text


@pytest.mark.parametrize("role", ["teacher", "admin"])
def test_staff_see_all_students(client, make_user, make_student, login, role):
    make_user(role, "staff@test.ru")
    p1 = make_user("parent", "p1@test.ru")
    make_student("Ребёнок Первый", parent_id=p1)
    make_student("Ребёнок Второй", parent_id=p1)
    login("staff@test.ru")
    r = client.get("/diary")
    assert "Ребёнок Первый" in r.text
    assert "Ребёнок Второй" in r.text


def test_diary_requires_login(client):
    r = client.get("/diary", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
