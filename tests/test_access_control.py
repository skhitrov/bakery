"""Role-based route guards and the `/` role router."""

import pytest


# --- unauthenticated access is always redirected to /login ---

@pytest.mark.parametrize("path", ["/", "/admin", "/diary"])
def test_anonymous_redirected_to_login(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


# --- GET /admin is teacher/admin only ---

def test_parent_cannot_open_admin(client, make_user, login):
    make_user("parent", "mum@test.ru")
    login("mum@test.ru")
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


@pytest.mark.parametrize("role", ["teacher", "admin"])
def test_staff_can_open_admin(client, make_user, login, role):
    make_user(role, "staff@test.ru")
    login("staff@test.ru")
    r = client.get("/admin")
    assert r.status_code == 200


# --- grid editing (/admin/save) is curator (admin role) only: reject teachers ---

@pytest.mark.parametrize("path", ["/admin/save"])
def test_teacher_blocked_from_admin_only_posts(client, make_user, login, path):
    make_user("teacher", "teach@test.ru")
    login("teach@test.ru")
    r = client.post(path, data={}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


# --- module/cohort management moved to teacher: the curator (admin role) is now blocked ---

@pytest.mark.parametrize(
    "path",
    ["/admin/add-module", "/admin/add-stream", "/admin/delete-module", "/admin/delete-stream"],
)
def test_curator_blocked_from_structure_posts(client, make_user, login, path):
    make_user("admin", "boss@test.ru")
    login("boss@test.ru")
    r = client.post(path, data={}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_module_cohort_management_shown_to_teacher_not_curator(client, make_user, login):
    # Teacher (admin@bulochka.ru) now manages modules + cohorts...
    make_user("teacher", "teach@test.ru")
    login("teach@test.ru")
    r = client.get("/admin")
    assert "Управление модулями" in r.text
    assert "Управление цехами" in r.text

    # ...and the curator (admin role) no longer sees those sections.
    make_user("admin", "cur@test.ru")
    login("cur@test.ru")
    r2 = client.get("/admin")
    assert "Управление модулями" not in r2.text
    assert "Управление цехами" not in r2.text


def test_parent_blocked_from_add_student(client, make_user, login):
    make_user("parent", "mum@test.ru")
    login("mum@test.ru")
    r = client.post("/admin/add-student", data={}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


# --- `/` routes by role ---

@pytest.mark.parametrize(
    "role,target",
    [("parent", "/diary"), ("teacher", "/admin"), ("admin", "/admin")],
)
def test_index_routes_by_role(client, make_user, login, role, target):
    make_user(role, "who@test.ru")
    login("who@test.ru")
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == target
