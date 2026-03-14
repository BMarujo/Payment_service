"""
Application configuration loaded from environment variables.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings — loaded from environment variables or .env file."""

    # ── Application ──────────────────────────
    app_name: str = Field(default="Payment Service")
    app_version: str = Field(default="1.0.0")
    debug: bool = Field(default=False)
    environment: str = Field(default="production")

    # ── API Security ─────────────────────────
    # Admin key for managing API keys (bootstrap key)
    admin_api_key: str = Field(default="change-me-in-production")

    # ── Database ─────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://payment_user:payment_pass@postgres:5432/payment_db"
    )

    # ── Redis ────────────────────────────────
    redis_url: str = Field(default="redis://redis:6379/0")

    # ── Stripe ───────────────────────────────
    stripe_secret_key: str = Field(default="sk_test_placeholder")
    stripe_publishable_key: str = Field(default="pk_test_placeholder")
    stripe_webhook_secret: str = Field(default="whsec_placeholder")

    # ── Rate Limiting ────────────────────────
    rate_limit_requests: int = Field(default=100)
    rate_limit_window_seconds: int = Field(default=60)

    # ── Logging ──────────────────────────────
    log_level: str = Field(default="INFO")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
