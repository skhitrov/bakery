from __future__ import annotations

import hashlib
import secrets
import time

from fastapi import Request, HTTPException
from itsdangerous import URLSafeTimedSerializer, URLSafeSerializer, BadSignature

from app.config import SECRET_KEY, SESSION_COOKIE
from app.database import get_db

_signer = URLSafeTimedSerializer(SECRET_KEY)
_csrf_signer = URLSafeSerializer(SECRET_KEY, salt="csrf")
_SALT = "session"
_SESSION_MAX_AGE = 86400  # 1 day

# --- Rate limiting ---
_login_attempts: dict[str, list[float]] = {}
_RATE_LIMIT_WINDOW = 300  # 5 minutes
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_BLOCK = 60  # block for 60 seconds after exceeding


def check_rate_limit(ip: str) -> bool:
    """Return True if the IP is allowed to attempt login."""
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    # Remove old attempts outside the window
    attempts = [t for t in attempts if now - t < _RATE_LIMIT_WINDOW]
    _login_attempts[ip] = attempts
    if len(attempts) >= _RATE_LIMIT_MAX:
        # Block if last attempt was within the block period
        if now - attempts[-1] < _RATE_LIMIT_BLOCK:
            return False
        # Block period passed, reset
        _login_attempts[ip] = []
    return True


def record_failed_login(ip: str) -> None:
    _login_attempts.setdefault(ip, []).append(time.time())


# --- Password hashing (scrypt) ---


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.scrypt(
        password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64
    )
    return f"scrypt:{salt}:{h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("scrypt:"):
        _, salt, h = stored.split(":", 2)
        computed = hashlib.scrypt(
            password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64
        )
        return computed.hex() == h
    # Legacy SHA-256 format: "salt:hex"
    salt, h = stored.split(":", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == h


def _rehash_if_legacy(user_id: int, password: str, stored: str) -> None:
    """Re-hash legacy SHA-256 passwords to scrypt on successful login."""
    if not stored.startswith("scrypt:"):
        with get_db() as conn:
            conn.execute(
                "UPDATE users SET password = ? WHERE id = ?",
                (hash_password(password), user_id),
            )


# --- Authentication ---


def authenticate(email: str, password: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    if row and verify_password(password, row["password"]):
        _rehash_if_legacy(row["id"], password, row["password"])
        return dict(row)
    return None


# --- Sessions ---


def create_session_cookie(user_id: int) -> str:
    return _signer.dumps(user_id, salt=_SALT)


def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        user_id = _signer.loads(token, salt=_SALT, max_age=_SESSION_MAX_AGE)
    except BadSignature:
        return None
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def require_user(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


# --- CSRF ---


def generate_csrf_token(user_id: int) -> str:
    return _csrf_signer.dumps(user_id)


def validate_csrf_token(token: str | None, user_id: int) -> bool:
    if not token:
        return False
    try:
        stored_id = _csrf_signer.loads(token)
        return stored_id == user_id
    except BadSignature:
        return False
