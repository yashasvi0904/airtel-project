"""Application settings, loaded from environment variables / .env (never from code)."""
from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Accel Business - Udyam Digital"
    environment: str = "development"

    # Storage. SQLite works out of the box; set a postgresql+psycopg:// URL for PostgreSQL.
    database_url: str = f"sqlite:///{(ROOT / 'storage' / 'udyam.db').as_posix()}"
    data_dir: Path = ROOT / "assignment" / "data"
    upload_dir: Path = ROOT / "storage" / "uploads"

    # Auth
    jwt_secret: str = "dev-only-change-me-please-use-32-plus-chars"
    jwt_expire_minutes: int = 60 * 12
    # Google Sign-In (OAuth client ID of type "Web application"). Public value; empty = Google buttons are disabled.
    google_client_id: str = ""
    admin_email: str = "admin@accel.example"
    admin_password: str = "ChangeMe!123"

    # "Today" for date based checks. The dataset README says to use 2026-07-15.
    # Set to empty to use the real system date.
    reference_date: str = "2026-07-15"

    # AI advisor. provider: auto | anthropic | mock
    llm_provider: str = "auto"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    llm_timeout_seconds: int = 25

    # Commercial assumption that is NOT in the supplied catalogue (see docs/ARCHITECTURE.md)
    gst_rate_percent: float = 18.0

    # Privacy
    document_retention_days: int = 30
    encryption_key: str = ""  # Fernet key; derived from jwt_secret if empty (dev only)
    cors_origins: str = "http://localhost:3000"

    @property
    def today(self) -> date:
        if self.reference_date:
            return date.fromisoformat(self.reference_date)
        return date.today()


@lru_cache
def get_settings() -> Settings:
    return Settings()
