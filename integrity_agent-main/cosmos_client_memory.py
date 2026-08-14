"""
In-memory implementation of CosmosIntegrityClient.

Drop-in replacement for demos and local development — no Azure Cosmos DB
account required. Data is lost when the process exits.

Usage (in .env):
    USE_MEMORY_STORE=true
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MemoryIntegrityClient:
    """Same interface as CosmosIntegrityClient, backed by plain dicts."""

    def __init__(self, **kwargs):
        self._sessions: dict[str, dict] = {}   # key: session_id
        self._reports: dict[str, dict] = {}    # key: report_id

    async def initialize(self) -> None:
        logger.info("MemoryIntegrityClient initialized (in-memory mode — no Cosmos DB).")

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    async def create_session(self, doc: dict) -> dict:
        sid = doc["id"]
        if sid in self._sessions:
            raise Exception("409 Conflict: session already exists.")
        self._sessions[sid] = doc
        logger.debug("Created in-memory session %s", sid)
        return doc

    async def get_session(self, session_id: str, student_id: str) -> Optional[dict]:
        session = self._sessions.get(session_id)
        if session is None or session.get("student_id") != student_id:
            return None
        return session

    async def upsert_session(self, doc: dict) -> dict:
        self._sessions[doc["id"]] = doc
        return doc

    async def get_all_sessions_for_student(
        self, student_id: str, lab_id: Optional[str] = None
    ) -> list[dict]:
        results = [
            s for s in self._sessions.values()
            if s.get("student_id") == student_id
        ]
        if lab_id:
            results = [s for s in results if s.get("lab_id") == lab_id]
        return results

    async def get_all_sessions_for_lab(
        self, lab_id: str, course_id: Optional[str] = None
    ) -> list[dict]:
        results = [
            s for s in self._sessions.values()
            if s.get("lab_id") == lab_id
        ]
        if course_id:
            results = [s for s in results if s.get("course_id") == course_id]
        return results

    # ------------------------------------------------------------------
    # Report operations
    # ------------------------------------------------------------------

    async def create_report(self, doc: dict) -> dict:
        self._reports[doc["id"]] = doc
        logger.debug("Created in-memory report %s", doc["id"])
        return doc

    async def get_report(self, report_id: str, student_id: str) -> Optional[dict]:
        report = self._reports.get(report_id)
        if report is None or report.get("student_id") != student_id:
            return None
        return report

    async def upsert_report(self, doc: dict) -> dict:
        self._reports[doc["id"]] = doc
        return doc

    async def get_reports_for_session(
        self, session_id: str, student_id: str
    ) -> list[dict]:
        return [
            r for r in self._reports.values()
            if r.get("session_id") == session_id
        ]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        logger.info("MemoryIntegrityClient closed.")
