"""
Orchestrator configuration.

All settings are read from environment variables (or a .env file).
Copy .env.example → .env to get started.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Agent base URLs ───────────────────────────────────────────────────────
    participant_url: str = "http://localhost:8001"
    companion_url: str = "http://localhost:8002"
    curriculum_url: str = "http://localhost:8003"
    assessment_url: str = "http://localhost:8004"
    integrity_url: str = "http://localhost:8005"

    # ── Integrity Agent auth ──────────────────────────────────────────────────
    integrity_token: str = ""

    # ── Session store ─────────────────────────────────────────────────────────
    # v0.1: in-memory.  v0.2: swap for Cosmos DB without touching the rest.
    session_ttl_seconds: int = 3600


settings = Settings()
