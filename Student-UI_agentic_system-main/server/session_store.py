"""In-memory session registry with TTL eviction.

The server owns all ``SessionState`` objects.  Clients receive only the
``session_id`` string.  A background sweep removes sessions that have been
idle longer than ``ttl_seconds`` to guard against clients that disconnect
without calling DELETE.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from agentic_system.models import SessionState

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 3600  # 1 hour


@dataclass
class _Entry:
    state: SessionState
    last_touched: float = field(default_factory=time.monotonic)


class SessionRegistry:
    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._sessions: dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def put(self, state: SessionState) -> None:
        with self._lock:
            self._sessions[state.session_id] = _Entry(state=state)

    def get(self, session_id: str) -> Optional[SessionState]:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return None
            entry.last_touched = time.monotonic()
            return entry.state

    def remove(self, session_id: str) -> Optional[SessionState]:
        with self._lock:
            entry = self._sessions.pop(session_id, None)
            return entry.state if entry else None

    def sweep_expired(self) -> int:
        now = time.monotonic()
        expired: list[str] = []
        with self._lock:
            for sid, entry in self._sessions.items():
                if now - entry.last_touched > self._ttl:
                    expired.append(sid)
            for sid in expired:
                del self._sessions[sid]
        if expired:
            logger.info("Evicted %d expired session(s)", len(expired))
        return len(expired)


async def run_ttl_sweep(registry: SessionRegistry, interval: int = 300) -> None:
    """Background coroutine that periodically evicts stale sessions."""
    while True:
        await asyncio.sleep(interval)
        registry.sweep_expired()
