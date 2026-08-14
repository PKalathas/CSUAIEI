"""
Curriculum Designer configuration.

All settings are read from environment variables (or a .env file).
Copy .env.example -> .env to get started.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Service ───────────────────────────────────────────────────────────────
    service_port: int = 8003
    service_name: str = "curriculum-designer"
    version: str = "0.1.0"

    # ── Azure OpenAI (Stage B) ────────────────────────────────────────────────
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment_name: str = "gpt-4o"   # env var: AZURE_OPENAI_DEPLOYMENT_NAME
    azure_openai_api_version: str = "2024-08-01-preview"

    # ── LLM backend ──────────────────────────────────────────────────────────
    # "azure" = real Azure OpenAI calls; "mock" = stub data for dev/test
    llm_backend: str = "azure"

    # ── Storage ───────────────────────────────────────────────────────────────
    # v0.1: in-memory.  v0.2: swap for "cosmos" without touching the rest.
    storage_backend: str = "memory"


settings = Settings()
