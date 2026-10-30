import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    database_url: str
    cors_origins: list[str]
    auth_mode: Literal["dev", "firebase"]
    firebase_project_id: str | None
    chat_requests_per_hour: int
    document_requests_per_hour: int


def _env(name: str, default: str | None = None) -> str | None:
    """Env var with surrounding whitespace removed (secrets piped in via stdin often end in a newline)."""
    value = os.getenv(name)
    value = value.strip() if value is not None else None
    return value or default


def get_settings() -> Settings:
    auth_mode = (_env("AUTH_MODE", "dev") or "dev").lower()
    if auth_mode not in ("dev", "firebase"):
        raise ValueError("AUTH_MODE must be 'dev' or 'firebase'")
    project = _env("FIREBASE_PROJECT_ID")
    if auth_mode == "firebase" and not project:
        raise ValueError("AUTH_MODE=firebase requires FIREBASE_PROJECT_ID")
    return Settings(
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_model=_env("GEMINI_MODEL", "gemini-2.5-flash"),
        # DATABASE_URL (e.g. Postgres) wins; DATABASE_PATH is a local SQLite file
        database_url=_env("DATABASE_URL") or _env("DATABASE_PATH", str(BACKEND_DIR / "carbon.db")),
        cors_origins=[o for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o],
        auth_mode=auth_mode,  # type: ignore[arg-type]
        firebase_project_id=project,
        chat_requests_per_hour=int(os.getenv("CHAT_REQUESTS_PER_HOUR", "60")),
        document_requests_per_hour=int(os.getenv("DOCUMENT_REQUESTS_PER_HOUR", "20")),
    )
