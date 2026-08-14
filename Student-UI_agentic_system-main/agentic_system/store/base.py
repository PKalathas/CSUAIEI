"""
Storage protocols for Participant and Guardian agents.

These are the abstract contracts. Any backend (SQLite today, an HTTP API
tomorrow, an in-memory mock in tests) only has to implement these methods.

Conventions:
  - All methods are synchronous. The embedder runs them off the event loop
    if it cares about async semantics (the Chainlit shell uses asyncio.to_thread).
  - Return shapes are plain dicts with stable keys, NOT Pydantic models.
    This keeps the protocol decoupled from the model layer and makes it
    trivial to back with a remote API that returns JSON.
  - `init()` is called once at construction time. `close()` is called on
    harness shutdown (best-effort; not all backends need it).
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


# --------------------------------------------------------------- Participant
@runtime_checkable
class ParticipantStore(Protocol):
    """Persistence for student-interaction telemetry.

    Backs `ParticipantAgent.log_interaction` and `get_student_context`.
    """

    def init(self) -> None:
        """Idempotent: create schema / verify connectivity."""

    def close(self) -> None:
        """Best-effort cleanup. May be a no-op."""

    def insert_interaction(self, item: dict) -> None:
        """
        Persist one interaction row. `item` keys:
          id, student_id, session_id, timestamp, message,
          question_type, hint_level, difficulty, response_time_ms, lab_id
        """

    def fetch_for_student(self, student_id: str) -> list[dict]:
        """Return ALL interactions for a student, oldest-first."""


# --------------------------------------------------------------- Guardian
@runtime_checkable
class GuardianStore(Protocol):
    """Persistence for integrity sessions, questions, violations, verifications.

    Backs `GuardianAgent` lifecycle / validate / verify operations.
    """

    def init(self) -> None: ...
    def close(self) -> None: ...

    # ----- session lifecycle -----
    def create_session(self, doc: dict) -> None:
        """
        `doc` keys: session_id, student_id, lab_id, course_id, started_at.
        Implementations should raise on duplicate session_id; the agent
        catches and treats it as idempotent.
        """

    def get_session(self, session_id: str, student_id: str) -> Optional[dict]:
        """
        Return the session doc with embedded `questions` and `violations`
        lists, or None if not found. Boolean fields (`escalated`,
        `report_generated`) are returned as Python bools.
        """

    def update_session_counters(
        self,
        session_id: str,
        student_id: str,
        *,
        question_count: int,
        violation_count: int,
        escalated: bool,
    ) -> None: ...

    def close_session(
        self,
        session_id: str,
        student_id: str,
        ended_at: str,
        report_id: Optional[str],
    ) -> None: ...

    # ----- per-record inserts -----
    def insert_question(self, session_id: str, student_id: str, record: dict) -> None: ...
    def insert_violation(self, session_id: str, student_id: str, record: dict) -> None: ...
    def insert_verification(
        self, session_id: str, student_id: str, record: dict
    ) -> None: ...


# --------------------------------------------------------------- System
@runtime_checkable
class SystemStore(Protocol):
    """Persistence for multi-tenant metadata: users, courses, enrollments.

    Orthogonal to the per-course `ParticipantStore` / `GuardianStore` —
    used by the server layer, not by the agents. Dict-in / dict-out.
    """

    def init(self) -> None: ...
    def close(self) -> None: ...

    # ----- users -----
    def insert_user(self, item: dict) -> None:
        """`item` keys: id, email, name, sso_subject, role, created_at."""

    def get_user(self, user_id: str) -> Optional[dict]: ...
    def get_user_by_email(self, email: str) -> Optional[dict]: ...
    def get_user_by_sso_subject(self, subject: str) -> Optional[dict]: ...
    def list_users(self) -> list[dict]: ...
    def update_user_sso_subject(self, user_id: str, sso_subject: str) -> None: ...
    def delete_user(self, user_id: str) -> None: ...

    # ----- courses -----
    def insert_course(self, item: dict) -> None:
        """`item` keys: id, name, instructor_id, blob_container_name,
        search_index_name, search_indexer_name, search_datasource_name,
        created_at."""

    def get_course(self, course_id: str) -> Optional[dict]: ...
    def list_courses(self, *, instructor_id: Optional[str] = None) -> list[dict]: ...
    def update_course(self, course_id: str, patch: dict) -> None: ...
    def delete_course(self, course_id: str) -> None: ...

    # ----- enrollments -----
    def insert_enrollment(self, course_id: str, user_id: str, enrolled_at: str) -> None: ...
    def delete_enrollment(self, course_id: str, user_id: str) -> None: ...
    def is_enrolled(self, course_id: str, user_id: str) -> bool: ...
    def list_enrolled_users(self, course_id: str) -> list[dict]: ...
    def list_courses_for_user(self, user_id: str) -> list[dict]: ...
