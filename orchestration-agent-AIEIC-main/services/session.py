"""
In-memory session store — v0.1.

Stores one SessionState per session_id, keyed by session_id.

Why in-memory for now:
  - Zero infrastructure overhead while the system is being built
  - Easy to reason about during development / testing

How to upgrade to Cosmos DB in v0.2:
  - Replace _sessions dict with Cosmos DB container reads/writes
  - SessionStore interface stays the same — nothing else in the codebase changes

What lives in a session:
  - conversation_history: supplied to Lab Companion on every turn (it's stateless)
  - integrity_flags: accumulated policy violations (for Policy Guardian in Phase 2)
  - turn count, timestamps
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from aieic_shared.schemas.companion import ChatMessage
from aieic_shared.schemas.core import LabPhase


class SessionState:
    """Mutable state for one student × lab session."""

    def __init__(self, session_id: str, student_id: str, lab_id: str) -> None:
        self.session_id = session_id
        self.student_id = student_id
        self.lab_id = lab_id
        self.phase: LabPhase = LabPhase.DURING_LAB
        self.conversation_turn_count: int = 0
        self.conversation_history: list[ChatMessage] = []
        self.integrity_flags: list[str] = []
        self.needs_instructor_review: bool = False
        self.created_at: datetime = datetime.utcnow()
        self.last_updated: datetime = datetime.utcnow()

    def add_turn(self, user_message: str, assistant_reply: str) -> None:
        """Append a completed user/assistant turn to history."""
        self.conversation_history.append(ChatMessage(role="user", content=user_message))
        self.conversation_history.append(ChatMessage(role="assistant", content=assistant_reply))
        self.conversation_turn_count += 1
        self.last_updated = datetime.utcnow()


class SessionStore:
    """Thread-safe (asyncio-safe) in-memory session store."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
    
    def get_or_create(
        self,
        student_id: str,
        lab_id: str,
        session_id: Optional[str] = None,
    ) -> tuple[SessionState, bool]:
        """
        Return a tuple of (session, created_new).

        created_new = False if an existing valid session was reused.
        created_new = True if a fresh session was created.

        A session is considered reusable only if:
        - the session_id exists in the store
        - the stored session belongs to the same student
        - the stored session belongs to the same lab
        """
        self._evict_expired()

        if session_id and session_id in self._sessions:
            sess = self._sessions[session_id]
            # Guard against session hijacking or stale IDs from different labs
            if sess.student_id == student_id and sess.lab_id == lab_id:
                return sess, False

        new_id = session_id or str(uuid.uuid4())
        sess = SessionState(session_id=new_id, student_id=student_id, lab_id=lab_id)
        self._sessions[new_id] = sess
        return sess, True

    def get(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)

    def _evict_expired(self) -> None:
        cutoff = datetime.utcnow() - self._ttl
        expired = [k for k, v in self._sessions.items() if v.last_updated < cutoff]
        for k in expired:
            del self._sessions[k]

    def delete(self, session_id: str) -> bool:
        """
        Delete a session from the store.

        Returns True if the session existed and was removed.
        Returns False if the session was not found.
        """
        return self._sessions.pop(session_id, None) is not None
