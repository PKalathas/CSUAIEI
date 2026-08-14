"""Lazy per-course `LabHarness` cache.

The server holds one ``HarnessRegistry`` and asks it for a harness whenever
a request is scoped to a course (e.g. ``POST /api/v1/courses/{id}/sessions``).
Each entry is constructed once and cached — it carries the course's own
SQLite stores (``data/courses/{id}/{participant,guardian}.db``) and its
own Azure AI Search index name, derived from the base ``SystemConfig`` via
``dataclasses.replace`` (no env reads here — that rule still belongs to
``SystemConfig.from_env``).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import replace
from pathlib import Path
from typing import Optional

from agentic_system import LabHarness, SystemConfig

logger = logging.getLogger(__name__)


class HarnessRegistry:
    """Thread-safe cache: course_id → LabHarness."""

    def __init__(self, *, base_config: SystemConfig, data_root: Path) -> None:
        self._base = base_config
        self._data_root = Path(data_root)
        self._cache: dict[str, LabHarness] = {}
        self._lock = threading.Lock()

    def get_or_create(self, course_id: str, course: dict) -> LabHarness:
        with self._lock:
            cached = self._cache.get(course_id)
            if cached is not None:
                return cached
            harness = self._build_for_course(course_id, course)
            self._cache[course_id] = harness
            return harness

    def evict(self, course_id: str) -> None:
        with self._lock:
            self._cache.pop(course_id, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def _build_for_course(self, course_id: str, course: dict) -> LabHarness:
        course_dir = self._data_root / "courses" / course_id
        participant_db = Path(
            course.get("participant_db_path") or (course_dir / "participant.db")
        )
        guardian_db = Path(
            course.get("guardian_db_path") or (course_dir / "guardian.db")
        )
        per_course_cfg = replace(
            self._base,
            course_id=course_id,
            participant_db_path=participant_db,
            guardian_db_path=guardian_db,
            azure_search_index=course.get("search_index_name", self._base.azure_search_index),
            azure_search_indexer_name=course.get(
                "search_indexer_name", self._base.azure_search_indexer_name
            ),
            azure_blob_container=course.get(
                "blob_container_name", self._base.azure_blob_container
            ),
        )
        logger.info(
            "Building LabHarness for course %s (kb_index=%s container=%s)",
            course_id,
            per_course_cfg.azure_search_index or "<none>",
            per_course_cfg.azure_blob_container or "<none>",
        )
        return LabHarness.build(config=per_course_cfg)

    # ----- helpers for routes -----------------------------------------------
    def peek(self, course_id: str) -> Optional[LabHarness]:
        with self._lock:
            return self._cache.get(course_id)
