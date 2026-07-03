"""Login / logout HTTP flow, session cookie, and rate limiting."""


def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "ПЕКАРНЯ" in r.text
    assert 'name="password"' in r.text


def test_valid_login_sets_session_cookie(client, make_user):
    make_user("admin", "boss@test.ru", "pass123")
    r = client.post(
        "/login",
        data={"email": "boss@test.ru", "password": "pass123"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    set_cookie = r.headers["set-cookie"].lower()
    assert "session=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie


def test_invalid_login_rejected(client, make_user):
    make_user("admin", "boss@test.ru", "pass123")
    r = client.post(
        "/login",
        data={"email": "boss@test.ru", "password": "WRONG"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "session=" not in r.headers.get("set-cookie", "")


def test_unknown_user_rejected(client):
    r = client.post(
        "/login",
        data={"email": "ghost@test.ru", "password": "whatever"},
        follow_redirects=False,
    )
    assert r.status_code == 401


def test_rate_limited_after_five_failures(client, make_user):
    make_user("admin", "boss@test.ru", "pass123")
    for _ in range(5):
        r = client.post(
            "/login",
            data={"email": "boss@test.ru", "password": "WRONG"},
            follow_redirects=False,
        )
        assert r.status_code == 401
    # 6th attempt is blocked regardless of credentials.
    r = client.post(
        "/login",
        data={"email": "boss@test.ru", "password": "pass123"},
        follow_redirects=False,
    )
    assert r.status_code == 429


def test_logout_clears_cookie(client, make_user, login):
    make_user("admin", "boss@test.ru", "pass123")
    login("boss@test.ru")
    r = client.get("/logout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    # deletion sends an expired/empty session cookie
    assert 'session=' in r.headers.get("set-cookie", "").lower()
