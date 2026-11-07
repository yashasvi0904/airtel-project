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

    # AI advisor. provider: auto (Anthropic if keyed, else Gemini if keyed, else built-in rules) | anthropic | gemini | mock
    llm_provider: str = "auto"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-lite-latest"
    gemini_fallback_models: str = "gemini-3.1-flash-lite,gemini-3.5-flash-lite"  # tried in order when the first model is out of free-tier quota
    llm_timeout_seconds: int = 25

    # Payments. gateway: sandbox (built-in test PSP, development only) | razorpay (live/test keys from the Razorpay dashboard)
    payment_gateway: str = "sandbox"
    payment_expiry_minutes: int = 15           # an unfinished attempt expires after this long
    payment_webhook_secret: str = "dev-webhook-secret-change-me"  # HMAC key for the sandbox gateway's webhooks
    sandbox_settle_seconds: float = 3.0        # how long the sandbox takes to "approve" a UPI request
    merchant_name: str = "Accel Business"
    merchant_vpa: str = "accel.business@sandbox"  # payee VPA shown in UPI intent / QR links
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

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
