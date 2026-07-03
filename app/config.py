import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "diary.db"
SESSION_COOKIE = "session"
# NOTE: kept at 6 to preserve the existing convention/tests; raising this to
# 10+ is recommended for production (see the security review).
MIN_PASSWORD_LENGTH = 6
# Upper bound guards against DoS via very long scrypt inputs.
MAX_PASSWORD_LENGTH = 128

_env_file = BASE_DIR / ".env"


def _load_secret_key() -> str:
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    # Try reading from an existing .env file
    if _env_file.exists():
        for line in _env_file.read_text().splitlines():
            if line.startswith("SECRET_KEY="):
                return line.split("=", 1)[1].strip()
    # Generate and persist a new key with owner-only (0600) permissions so the
    # signing key that protects all sessions/CSRF tokens isn't world-readable.
    key = secrets.token_hex(32)
    try:
        fd = os.open(_env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"SECRET_KEY={key}\n")
        return key
    except FileExistsError:
        # Created concurrently (multi-worker first boot) or exists without a key.
        for line in _env_file.read_text().splitlines():
            if line.startswith("SECRET_KEY="):
                return line.split("=", 1)[1].strip()
        with open(_env_file, "a") as f:
            f.write(f"SECRET_KEY={key}\n")
        os.chmod(_env_file, 0o600)
        return key


SECRET_KEY = _load_secret_key()
