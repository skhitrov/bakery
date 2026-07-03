"""Regression tests for the DevSecOps hardening pass.

Each test pins a specific fix so it can't silently regress:
security headers, Secure-cookie gating, X-Forwarded-For trust, session
revocation, malformed-input handling, and the stored-XSS fix.
"""


def test_security_headers_present(client):
    r = client.get("/login")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    # No 'unsafe-inline' in script-src — the strict policy is the XSS backstop.
    assert "unsafe-inline" not in r.headers["content-security-policy"]


def test_session_cookie_secure_only_over_https(client, make_user):
    make_user("admin", "boss@test.ru", "pass123")
    creds = {"email": "boss@test.ru", "password": "pass123"}

    # Plain HTTP: no Secure flag, so the (currently HTTP-only) prod box still works.
    r = client.post("/login", data=creds, follow_redirects=False)
    assert "secure" not in r.headers["set-cookie"].lower()

    # Behind a TLS-terminating proxy (X-Forwarded-Proto: https): Secure is set.
    r2 = client.post(
        "/login", data=creds, headers={"X-Forwarded-Proto": "https"}, follow_redirects=False
    )
    assert "secure" in r2.headers["set-cookie"].lower()


def test_xforwarded_for_cannot_bypass_rate_limit(client, make_user):
    make_user("admin", "boss@test.ru", "pass123")
    # Five failures, each with a *different* spoofed client IP.
    for i in range(5):
        r = client.post(
            "/login",
            data={"email": "boss@test.ru", "password": "WRONG"},
            headers={"X-Forwarded-For": f"9.9.9.{i}"},
            follow_redirects=False,
        )
        assert r.status_code == 401
    # A brand-new spoofed IP must NOT reset the bucket — untrusted XFF is ignored.
    r = client.post(
        "/login",
        data={"email": "boss@test.ru", "password": "pass123"},
        headers={"X-Forwarded-For": "1.2.3.4"},
        follow_redirects=False,
    )
    assert r.status_code == 429


def test_logout_without_csrf_is_forbidden(client, make_user, login):
    make_user("admin", "boss@test.ru", "pass123")
    login("boss@test.ru")
    r = client.post("/logout", data={}, follow_redirects=False)
    assert r.status_code == 403


def test_logout_revokes_existing_session_token(client, make_user, login, csrf):
    uid = make_user("admin", "boss@test.ru", "pass123")
    login("boss@test.ru")
    old_cookie = client.cookies["session"]
    # Sanity: the session is valid.
    assert client.get("/", follow_redirects=False).headers["location"] == "/admin"

    client.post("/logout", data={"csrf_token": csrf(uid)}, follow_redirects=False)

    # Replaying the pre-logout cookie is rejected (session_version was bumped).
    r = client.get(
        "/admin", headers={"Cookie": f"session={old_cookie}"}, follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_password_change_revokes_parent_session(client, make_user, login, csrf):
    tid = make_user("teacher", "t@test.ru")
    pid = make_user("parent", "p@mail.ru", "oldpass")
    login("t@test.ru")
    r = client.post(
        "/admin/change-password",
        data={"csrf_token": csrf(tid), "user_id": str(pid), "new_password": "brandnew1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # The parent's session_version advanced, invalidating any live cookie.
    from app.database import get_db

    with get_db() as conn:
        sv = conn.execute(
            "SELECT session_version FROM users WHERE id = ?", (pid,)
        ).fetchone()[0]
    assert sv == 1


def test_malformed_id_returns_redirect_not_500(client, make_user, login, csrf):
    tid = make_user("teacher", "t@test.ru")
    login("t@test.ru")
    for path, field in [
        ("/admin/delete-student", "student_id"),
        ("/admin/change-password", "user_id"),
    ]:
        r = client.post(
            path,
            data={"csrf_token": csrf(tid), field: "not-a-number"},
            follow_redirects=False,
        )
        assert r.status_code == 303  # clean redirect, never a 500


def test_student_name_is_not_executable_in_delete_confirm(client, make_user, make_student, login):
    make_user("teacher", "t@test.ru")
    make_student("'); alert(document.cookie)//")
    login("t@test.ru")
    html = client.get("/admin").text
    # The name is carried in a data-confirm attribute (a plain JS string read via
    # getAttribute) — never an inline onsubmit handler — and the breakout
    # sequence is HTML-escaped, so it can't terminate a confirm('...') string.
    assert "onsubmit" not in html
    assert "data-confirm=" in html
    assert "'); alert(document.cookie)//" not in html
