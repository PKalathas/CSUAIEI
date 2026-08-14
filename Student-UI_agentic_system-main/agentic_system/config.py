"""
Configuration for the harness.

`SystemConfig` is a plain dataclass — no implicit env loading. Embedders
that want env-driven config call `SystemConfig.from_env()`; embedders that
want to drive everything from their own settings system construct it
directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass(frozen=True)
class SystemConfig:
    # ---- Identity ----------------------------------------------------------
    student_id: str = "default-student"
    lab_id: str = "default-lab"
    course_id: str = "CSC580"

    # ---- Storage paths (defaults; overridden when injecting custom stores) -
    participant_db_path: Path = field(default_factory=lambda: Path("data/participant.db"))
    guardian_db_path: Path = field(default_factory=lambda: Path("data/guardian.db"))

    # ---- Multi-tenant storage roots ---------------------------------------
    data_root: Path = field(default_factory=lambda: Path("data"))
    system_db_path: Path = field(default_factory=lambda: Path("data/system.db"))

    # ---- Auth (Cal Poly CAS + session JWT + dev bypass) -------------------
    # CAS web SSO. ``cas_service_url`` is the single source of truth for the
    # ``service`` parameter — it must be byte-for-byte identical on the login
    # redirect and the back-channel ticket validation, so the server uses its
    # own copy and never trusts a client-supplied value.
    cas_base_url: str = ""
    cas_service_url: str = ""
    cas_email_domain: str = "calpoly.edu"
    # Server-minted session token (Bearer) the API verifies on every request.
    session_jwt_secret: str = ""
    session_jwt_ttl: int = 28800  # 8 hours
    # Local-dev escape hatch: skip the real CAS redirect/validation and
    # authenticate a fixed mock netid. Mirrors ``dev_auth_bypass`` philosophy.
    cas_mock: bool = False
    admin_email: str = ""
    dev_auth_bypass: bool = False
    dev_user_id: str = ""

    # ---- Azure OpenAI ------------------------------------------------------
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-12-01-preview"

    # ---- Knowledge base (Azure AI Search) — optional -----------------------
    azure_search_endpoint: str = ""
    azure_search_api_key: str = ""
    azure_search_index: str = ""
    azure_search_admin_key: str = ""
    azure_search_indexer_name: str = ""

    # ---- Blob storage (for instructor uploads) — optional -----------------
    azure_blob_connection_string: str = ""
    azure_blob_container: str = ""

    # ---- Tutoring knobs ----------------------------------------------------
    rag_top_n: int = 3
    rag_max_content_chars: int = 1000
    history_keep_turns: int = 6
    verifier_max_retries: int = 2

    # ---- Properties --------------------------------------------------------
    @property
    def indexing_enabled(self) -> bool:
        return bool(
            self.azure_blob_connection_string
            and self.azure_blob_container
            and self.azure_search_endpoint
            and self.azure_search_admin_key
            and self.azure_search_indexer_name
        )

    @property
    def search_enabled(self) -> bool:
        return bool(
            self.azure_search_endpoint
            and self.azure_search_api_key
            and self.azure_search_index
        )

    @property
    def llm_configured(self) -> bool:
        return bool(
            self.azure_openai_endpoint
            and self.azure_openai_api_key
            and self.azure_openai_deployment
        )

    @property
    def cas_enabled(self) -> bool:
        """True when real CAS SSO is fully configured (mock excluded)."""
        return bool(
            self.cas_base_url
            and self.cas_service_url
            and self.session_jwt_secret
        )

    # ---- Constructors ------------------------------------------------------
    @classmethod
    def from_env(cls, **overrides) -> "SystemConfig":
        """Build a config from environment variables. Overrides win.

        Embedders that don't want env-driven config should construct
        `SystemConfig(...)` directly instead of calling this.
        """
        base = cls(
            student_id=os.getenv("STUDENT_ID", "default-student"),
            lab_id=os.getenv("LAB_ID", "default-lab"),
            course_id=os.getenv("COURSE_ID", "CSC580"),
            participant_db_path=Path(
                os.getenv("PARTICIPANT_DB_PATH", "data/participant.db")
            ),
            guardian_db_path=Path(
                os.getenv("GUARDIAN_DB_PATH", "data/guardian.db")
            ),
            data_root=Path(os.getenv("DATA_ROOT", "data")),
            system_db_path=Path(os.getenv("SYSTEM_DB_PATH", "data/system.db")),
            cas_base_url=os.getenv("CAS_BASE_URL", ""),
            cas_service_url=os.getenv("CAS_SERVICE_URL", ""),
            cas_email_domain=os.getenv("CAS_EMAIL_DOMAIN", "calpoly.edu"),
            session_jwt_secret=os.getenv("SESSION_JWT_SECRET", ""),
            session_jwt_ttl=int(os.getenv("SESSION_JWT_TTL", "28800")),
            cas_mock=os.getenv("CAS_MOCK", "").lower() in ("1", "true", "yes"),
            admin_email=os.getenv("ADFEL_ADMIN_EMAIL", ""),
            dev_auth_bypass=os.getenv("ADFEL_DEV_AUTH_BYPASS", "").lower() in ("1", "true", "yes"),
            dev_user_id=os.getenv("ADFEL_DEV_USER_ID", ""),
            azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", ""),
            azure_openai_api_version=os.getenv(
                "AZURE_OPENAI_API_VERSION", "2024-12-01-preview"
            ),
            azure_search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT", ""),
            azure_search_api_key=os.getenv("AZURE_SEARCH_API_KEY", ""),
            azure_search_index=os.getenv("AZURE_SEARCH_INDEX_NAME", ""),
            azure_search_admin_key=os.getenv("AZURE_SEARCH_ADMIN_KEY", ""),
            azure_search_indexer_name=os.getenv("AZURE_SEARCH_INDEXER_NAME", ""),
            azure_blob_connection_string=os.getenv("AZURE_BLOB_CONNECTION_STRING", ""),
            azure_blob_container=os.getenv("AZURE_BLOB_CONTAINER_NAME", ""),
            rag_top_n=int(os.getenv("RAG_TOP_N", "3")),
            rag_max_content_chars=int(os.getenv("RAG_MAX_CONTENT_LENGTH", "1000")),
            history_keep_turns=int(os.getenv("HISTORY_KEEP_TURNS", "6")),
            verifier_max_retries=int(os.getenv("VERIFIER_MAX_RETRIES", "2")),
        )
        return replace(base, **overrides) if overrides else base
