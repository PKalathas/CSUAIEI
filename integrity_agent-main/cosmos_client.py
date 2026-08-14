import logging
from typing import Optional

from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey, exceptions as cosmos_exceptions

logger = logging.getLogger(__name__)

SESSIONS_CONTAINER = "sessions"
REPORTS_CONTAINER = "reports"


class CosmosIntegrityClient:
    """Async Azure Cosmos DB client for the Integrity Guardian."""

    def __init__(self, url: str, key: str, database: str = "integrity_guardian"):
        self._client = CosmosClient(url, credential=key)
        self._db_name = database
        self._sessions = None
        self._reports = None

    async def initialize(self) -> None:
        """Create the database and containers if they do not already exist."""
        db = await self._client.create_database_if_not_exists(id=self._db_name)
        self._sessions = await db.create_container_if_not_exists(
            id=SESSIONS_CONTAINER,
            partition_key=PartitionKey(path="/student_id"),
        )
        self._reports = await db.create_container_if_not_exists(
            id=REPORTS_CONTAINER,
            partition_key=PartitionKey(path="/student_id"),
        )
        logger.info(
            "Cosmos DB initialized: database=%s, containers=[%s, %s]",
            self._db_name,
            SESSIONS_CONTAINER,
            REPORTS_CONTAINER,
        )

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    async def create_session(self, doc: dict) -> dict:
        """Insert a new session document. Raises ConflictError if id exists."""
        result = await self._sessions.create_item(body=doc)
        logger.debug("Created session %s for student %s", doc["id"], doc["student_id"])
        return result

    async def get_session(self, session_id: str, student_id: str) -> Optional[dict]:
        """Point-read a session by id + partition key. Returns None if not found."""
        try:
            item = await self._sessions.read_item(
                item=session_id, partition_key=student_id
            )
            return item
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return None

    async def upsert_session(self, doc: dict) -> dict:
        """Insert or replace a session document."""
        result = await self._sessions.upsert_item(body=doc)
        return result

    async def get_all_sessions_for_student(
        self, student_id: str, lab_id: Optional[str] = None
    ) -> list[dict]:
        """Query all sessions for a given student, optionally filtered by lab_id."""
        if lab_id:
            query = (
                "SELECT * FROM c WHERE c.student_id = @sid AND c.lab_id = @lid"
            )
            params = [
                {"name": "@sid", "value": student_id},
                {"name": "@lid", "value": lab_id},
            ]
        else:
            query = "SELECT * FROM c WHERE c.student_id = @sid"
            params = [{"name": "@sid", "value": student_id}]

        results = []
        async for item in self._sessions.query_items(
            query=query,
            parameters=params,
            partition_key=student_id,
        ):
            results.append(item)
        return results

    async def get_all_sessions_for_lab(
        self, lab_id: str, course_id: Optional[str] = None
    ) -> list[dict]:
        """Cross-student query: all sessions for a given lab, optionally filtered by course_id."""
        if course_id:
            query = (
                "SELECT * FROM c WHERE c.lab_id = @lab_id AND c.course_id = @cid"
            )
            params = [
                {"name": "@lab_id", "value": lab_id},
                {"name": "@cid", "value": course_id},
            ]
        else:
            query = "SELECT * FROM c WHERE c.lab_id = @lab_id"
            params = [{"name": "@lab_id", "value": lab_id}]

        results = []
        async for item in self._sessions.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True,
        ):
            results.append(item)
        return results

    # ------------------------------------------------------------------
    # Report operations
    # ------------------------------------------------------------------

    async def create_report(self, doc: dict) -> dict:
        """Insert a new report document."""
        result = await self._reports.create_item(body=doc)
        logger.debug("Created report %s for student %s", doc["id"], doc["student_id"])
        return result

    async def get_report(self, report_id: str, student_id: str) -> Optional[dict]:
        """Point-read a report by id + partition key. Returns None if not found."""
        try:
            item = await self._reports.read_item(
                item=report_id, partition_key=student_id
            )
            return item
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return None

    async def upsert_report(self, doc: dict) -> dict:
        """Insert or replace a report document."""
        result = await self._reports.upsert_item(body=doc)
        return result

    async def get_reports_for_session(
        self, session_id: str, student_id: str
    ) -> list[dict]:
        """Return all reports linked to a specific session."""
        query = (
            "SELECT * FROM c WHERE c.student_id = @sid AND c.session_id = @sess"
        )
        params = [
            {"name": "@sid", "value": student_id},
            {"name": "@sess", "value": session_id},
        ]
        results = []
        async for item in self._reports.query_items(
            query=query,
            parameters=params,
            partition_key=student_id,
        ):
            results.append(item)
        return results

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._client.close()
        logger.info("Cosmos DB client closed.")
