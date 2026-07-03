from __future__ import annotations

import hashlib
import secrets
import time

from fastapi import Request, HTTPException
from itsdangerous import URLSafeTimedSerializer, BadData

from app.config import SECRET_KEY, SESSION_COOKIE
from app.database import get_db

_signer = URLSafeTimedSerializer(SECRET_KEY)
# Timed serializer so CSRF tokens expire (was URLSafeSerializer = never-expiring).
_csrf_signer = URLSafeTimedSerializer(SECRET_KEY, salt="csrf")
_SALT = "session"
_SESSION_MAX_AGE = 86400  # 1 day
_CSRF_MAX_AGE = 86400  # 1 day

# --- Rate limiting ---
_login_attempts: dict[str, list[float]] = {}
_RATE_LIMIT_WINDOW = 300  # 5 minutes
_RATE_LIMIT_MAX = 5


def check_rate_limit(ip: str) -> bool:
    """Return True if the IP is allowed to attempt login.

    Blocks once >= _RATE_LIMIT_MAX failures accumulate within the sliding
    window (previously the counter was fully reset after a 60s block, which
    allowed ~5 guesses/minute indefinitely). Empty buckets are dropped so the
    in-memory dict cannot grow without bound.
    """
    now = time.time()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < _RATE_LIMIT_WINDOW]
    if attempts:
        _login_attempts[ip] = attempts
    else:
        _login_attempts.pop(ip, None)
    return len(attempts) < _RATE_LIMIT_MAX


def record_failed_login(ip: str) -> None:
    _login_attempts.setdefault(ip, []).append(time.time())


# --- Password hashing (scrypt) ---
# NOTE: n=16384 (~16 MB/hash) is kept deliberately: the target server has only
# 512 MB RAM, and the OWASP-recommended n=2**17 would use ~134 MB per concurrent
# login and risk OOM. Revisit if the app moves to a larger host.


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.scrypt(
        password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64
    )
    return f"scrypt:{salt}:{h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("scrypt:"):
        try:
            _, salt, h = stored.split(":", 2)
        except ValueError:
            return False
        computed = hashlib.scrypt(
            password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64
        )
        return secrets.compare_digest(computed.hex(), h)
    # Legacy SHA-256 format: "salt:hex"
    try:
        salt, h = stored.split(":", 1)
    except ValueError:
        return False
    computed = hashlib.sha256((salt + password).encode()).hexdigest()
    return secrets.compare_digest(computed, h)


def _rehash_if_legacy(user_id: int, password: str, stored: str) -> None:
    """Re-hash legacy SHA-256 passwords to scrypt on successful login."""
    if not stored.startswith("scrypt:"):
        with get_db() as conn:
            conn.execute(
                "UPDATE users SET password = ? WHERE id = ?",
                (hash_password(password), user_id),
            )


# --- Authentication ---

# A throwaway hash so authenticate() spends the same scrypt time whether or not
# the email exists — prevents timing-based user enumeration.
_DUMMY_HASH = hash_password("timing-equalizer")


def authenticate(email: str, password: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    if row is None:
        verify_password(password, _DUMMY_HASH)  # equalize timing on the miss path
        return None
    if verify_password(password, row["password"]):
        _rehash_if_legacy(row["id"], password, row["password"])
        return dict(row)
    return None


# --- Sessions ---


def create_session_cookie(user_id: int, session_version: int = 0) -> str:
    return _signer.dumps({"uid": user_id, "v": session_version}, salt=_SALT)


def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        payload = _signer.loads(token, salt=_SALT, max_age=_SESSION_MAX_AGE)
    except BadData:
        return None
    # Reject legacy bare-int cookies (from before session versioning) — forces a
    # clean re-login rather than raising on the dict access below.
    if not isinstance(payload, dict):
        return None
    user_id = payload.get("uid")
    version = payload.get("v")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    # Session revocation: a logout / password change bumps session_version,
    # invalidating every previously issued cookie for that user.
    if row["session_version"] != version:
        return None
    return dict(row)


def bump_session_version(user_id: int) -> None:
    """Invalidate all outstanding sessions for a user (logout, password change)."""
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET session_version = session_version + 1 WHERE id = ?",
            (user_id,),
        )


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
        stored_id = _csrf_signer.loads(token, max_age=_CSRF_MAX_AGE)
    except BadData:
        return False
    return stored_id == user_id
