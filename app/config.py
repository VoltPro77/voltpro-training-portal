"""Loads configuration from environment (.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STORAGE_DIR = ROOT / "storage" / "videos"

load_dotenv(ROOT / ".env")

DATA_DIR.mkdir(exist_ok=True)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def secret_key():
    return os.environ.get("SECRET_KEY", "dev-only-insecure-key")


def database_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return f"sqlite:///{DATA_DIR / 'portal.db'}"
    # Render/Heroku-style URLs sometimes use postgres:// which SQLAlchemy 2.x rejects
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def storage_backend():
    return os.environ.get("STORAGE_BACKEND", "local").strip().lower()


def r2_config():
    return {
        "account_id": os.environ.get("R2_ACCOUNT_ID", "").strip(),
        "access_key_id": os.environ.get("R2_ACCESS_KEY_ID", "").strip(),
        "secret_access_key": os.environ.get("R2_SECRET_ACCESS_KEY", "").strip(),
        "bucket_name": os.environ.get("R2_BUCKET_NAME", "").strip(),
        "public_base_url": os.environ.get("R2_PUBLIC_BASE_URL", "").strip(),
    }


def anthropic_api_key():
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


def admin_seed():
    return {
        "name": os.environ.get("ADMIN_NAME", "Admin"),
        "username": os.environ.get("ADMIN_USERNAME", "admin"),
        "password": os.environ.get("ADMIN_PASSWORD", "changeme"),
    }


def port():
    try:
        return int(os.environ.get("PORT", "5060"))
    except ValueError:
        return 5060
