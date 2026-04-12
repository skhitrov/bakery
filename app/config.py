import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "diary.db"
SESSION_COOKIE = "session"
MIN_PASSWORD_LENGTH = 6

_env_file = BASE_DIR / ".env"


def _load_secret_key() -> str:
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    # Try reading from .env file
    if _env_file.exists():
        for line in _env_file.read_text().splitlines():
            if line.startswith("SECRET_KEY="):
                return line.split("=", 1)[1].strip()
    # Generate and persist a new key
    key = secrets.token_hex(32)
    with open(_env_file, "a") as f:
        f.write(f"SECRET_KEY={key}\n")
    return key


SECRET_KEY = _load_secret_key()
