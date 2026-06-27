from __future__ import annotations

"""
Phase 9: Platform configuration.

All settings are read from environment variables (with a .env fallback).
Override any value by setting the corresponding PLATFORM_* env var.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class PlatformSettings(BaseSettings):
    """
    Runtime configuration for the RetroDecrypt Platform.

    All fields can be overridden via environment variables prefixed
    with PLATFORM_ (e.g. PLATFORM_DATABASE_URL=postgresql://...).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PLATFORM_",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_NAME:      str       = "RetroDecrypt Platform"
    APP_VERSION:   str       = "1.0.0"
    DEBUG:         bool      = False
    ALLOWED_HOSTS: str       = "*"
    ALLOWED_ORIGINS: list[str] = ["*"]

    # ------------------------------------------------------------------
    # Database (PostgreSQL for production, SQLite for dev/test)
    # ------------------------------------------------------------------
    DATABASE_URL: str = (
        "postgresql://postgres:postgres@localhost:5432/java_intelligence"
    )

    # ------------------------------------------------------------------
    # JWT Authentication
    # ------------------------------------------------------------------
    SECRET_KEY:                     str = "change-this-secret-key-in-production-min-32-chars"
    ALGORITHM:                      str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:    int = 30
    REFRESH_TOKEN_EXPIRE_DAYS:      int = 7

    # ------------------------------------------------------------------
    # RBAC
    # ------------------------------------------------------------------
    # Default role assigned to new registrations
    DEFAULT_USER_ROLE: str = "viewer"

    # ------------------------------------------------------------------
    # Repository storage
    # ------------------------------------------------------------------
    # Base directory for per-repository data (metadata, graphs, vectordb)
    REPOSITORIES_DATA_DIR: str = str(
        Path(__file__).parent.parent.parent / "data" / "repositories"
    )

    # ------------------------------------------------------------------
    # Background jobs
    # ------------------------------------------------------------------
    MAX_CONCURRENT_JOBS: int = 4
    JOB_TIMEOUT_SECONDS: int = 3600  # 1 hour per job

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 120

    # ------------------------------------------------------------------
    # First-run admin bootstrap
    # ------------------------------------------------------------------
    BOOTSTRAP_ADMIN_EMAIL:    str = "admin@example.com"
    BOOTSTRAP_ADMIN_USERNAME: str = "admin"
    BOOTSTRAP_ADMIN_PASSWORD: str = "ChangeMe123!"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
settings = PlatformSettings()
