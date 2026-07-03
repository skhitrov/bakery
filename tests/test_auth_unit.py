"""Unit tests for the pure helpers in app.auth (no HTTP, no DB)."""

import hashlib

from app.auth import (
    hash_password,
    verify_password,
    generate_csrf_token,
    validate_csrf_token,
    check_rate_limit,
    record_failed_login,
)


class TestPasswordHashing:
    def test_hash_format_is_scrypt(self):
        h = hash_password("secret123")
        assert h.startswith("scrypt:")
        assert len(h.split(":")) == 3

    def test_roundtrip(self):
        h = hash_password("correct horse")
        assert verify_password("correct horse", h) is True

    def test_wrong_password_rejected(self):
        h = hash_password("right")
        assert verify_password("wrong", h) is False

    def test_salt_is_random(self):
        assert hash_password("same") != hash_password("same")

    def test_legacy_sha256_still_verifies(self):
        # Legacy format is "salt:sha256(salt + password)".
        salt = "abc123"
        pw = "legacypw"
        digest = hashlib.sha256((salt + pw).encode()).hexdigest()
        stored = f"{salt}:{digest}"
        assert verify_password(pw, stored) is True
        assert verify_password("nope", stored) is False


class TestCSRF:
    def test_roundtrip(self):
        token = generate_csrf_token(42)
        assert validate_csrf_token(token, 42) is True

    def test_wrong_user_rejected(self):
        token = generate_csrf_token(42)
        assert validate_csrf_token(token, 43) is False

    def test_none_rejected(self):
        assert validate_csrf_token(None, 1) is False

    def test_tampered_token_rejected(self):
        token = generate_csrf_token(7)
        assert validate_csrf_token(token + "x", 7) is False


class TestRateLimiter:
    def test_allows_up_to_five_then_blocks(self):
        ip = "10.0.0.1"
        for _ in range(5):
            assert check_rate_limit(ip) is True
            record_failed_login(ip)
        # 6th attempt within the block window is refused.
        assert check_rate_limit(ip) is False

    def test_isolated_per_ip(self):
        for _ in range(5):
            record_failed_login("10.0.0.2")
        assert check_rate_limit("10.0.0.2") is False
        assert check_rate_limit("10.0.0.3") is True
