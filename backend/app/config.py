"""Application configuration, loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _csv_env(name: str, default: str = "") -> tuple[str, ...]:
    """Return a normalized, non-empty comma-separated environment setting."""
    return tuple(item.strip().rstrip("/") for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    # Metadata (application) database — owns users/projects/scenarios/runs.
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://locklens:locklens_dev_pw@127.0.0.1:5432/locklens"
    )
    # Lab database — the ONLY database experiment SQL may touch. Separate by design.
    lab_database_url: str = os.getenv(
        "LAB_DATABASE_URL", "postgresql://locklens_lab:locklens_lab_pw@127.0.0.1:5432/locklens_lab"
    )
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-only-insecure-secret-change-me")
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", "86400"))
    # Execution safety bounds
    statement_timeout_ms: int = int(os.getenv("LAB_STATEMENT_TIMEOUT_MS", "10000"))
    lock_timeout_ms: int = int(os.getenv("LAB_LOCK_TIMEOUT_MS", "8000"))
    max_step_rows: int = int(os.getenv("LAB_MAX_STEP_ROWS", "500"))
    max_steps_per_tx: int = int(os.getenv("MAX_STEPS_PER_TX", "40"))
    max_transactions: int = int(os.getenv("MAX_TRANSACTIONS", "4"))
    run_hard_timeout_seconds: int = int(os.getenv("RUN_HARD_TIMEOUT_SECONDS", "120"))
    lock_poll_interval_ms: int = int(os.getenv("LOCK_POLL_INTERVAL_MS", "50"))
    environment: str = os.getenv("ENVIRONMENT", "development")
    cors_origins: tuple[str, ...] = _csv_env("CORS_ORIGINS")


settings = Settings()
