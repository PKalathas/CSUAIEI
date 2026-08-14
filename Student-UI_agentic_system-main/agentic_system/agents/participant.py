"""
Participant Agent — learning-context tracker.

Pure constructor injection: takes a `ParticipantStore`, an `LLMClient`, and
the active config. No globals; no env reads at runtime.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..config import SystemConfig
from ..llm import LLMClient
from ..models import StudentContext
from ..store.base import ParticipantStore

logger = logging.getLogger(__name__)


class ParticipantAgent:
    def __init__(
        self,
        *,
        store: ParticipantStore,
        llm: LLMClient,
        config: SystemConfig,
    ) -> None:
        self._store = store
        self._llm = llm
        self._config = config
        self._store.init()

    # ------------------------------------------------------------------ LLM
    def classify_question(self, message: str) -> dict:
        """LLM classification of one student message. Fail-safe to a neutral default."""
        prompt = (
            "Analyze this student question and classify it.\n\n"
            f"Question: {message[:500]}\n\n"
            "Return a JSON object with:\n"
            '- question_type: one of "debugging", "concept", "setup", "other"\n'
            "- hint_level: 1 (simple hint needed), 2 (explain error), 3 (point to docs)\n"
            '- difficulty: one of "low", "medium", "high"\n\n'
            "Return ONLY valid JSON, no other text."
        )
        try:
            raw = self._llm.complete(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=120,
                json_mode=True,
            )
            return json.loads(raw)
        except Exception as e:
            logger.warning("Classification failed (fail-safe applied): %s", e)
            return {"question_type": "other", "hint_level": 1, "difficulty": "medium"}

    # ------------------------------------------------------------------ writes
    def log_interaction(
        self,
        *,
        student_id: str,
        session_id: str,
        message: str,
        response_time_ms: Optional[int] = None,
    ) -> str:
        classification = self.classify_question(message)
        interaction_id = str(uuid.uuid4())
        item = {
            "id": interaction_id,
            "student_id": student_id,
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message[:500],
            "question_type": classification.get("question_type", "other"),
            "hint_level": int(classification.get("hint_level", 1)),
            "difficulty": classification.get("difficulty", "medium"),
            "response_time_ms": response_time_ms or 0,
            "lab_id": self._config.lab_id,
        }
        self._store.insert_interaction(item)
        return interaction_id

    # ------------------------------------------------------------------ reads
    def _generate_summary(
        self,
        *,
        total: int,
        type_counts: dict,
        avg_hint: float,
        sessions_count: int,
        avg_questions_per_session: float,
        primary_type: str,
    ) -> str:
        """LLM-powered narrative summary; rule-based fallback on any failure."""
        prompt = (
            "You are a learning analytics assistant. Generate a concise 2-3 "
            "sentence summary of a student's learning behavior for a tutoring "
            "AI to use as context.\n\n"
            f"Student stats:\n"
            f"- Total questions: {total} across {sessions_count} session(s)\n"
            f"- Questions per session (avg): {avg_questions_per_session:.1f}\n"
            f"- Question type breakdown: {type_counts}\n"
            f"- Primary question type: {primary_type}\n"
            f"- Average hint level needed: {avg_hint:.1f} "
            "(1=minimal, 2=explain error, 3=point to docs)\n\n"
            "Write a helpful, actionable summary that tells the tutor how to "
            "best support this student. Be specific. No bullet points."
        )
        try:
            return self._llm.complete(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=180,
            )
        except Exception as e:
            logger.warning("Summary LLM failed; using rule-based fallback: %s", e)
            summary = (
                f"Student has asked {total} questions across "
                f"{sessions_count} session(s). Primary focus: "
                f"{primary_type} questions. "
            )
            if avg_hint > 2:
                summary += "Often needs detailed explanations."
            elif avg_hint > 1.5:
                summary += "Moderate assistance level."
            else:
                summary += "Often understands with minimal hints."
            return summary

    def get_student_context(self, student_id: str) -> StudentContext:
        items = self._store.fetch_for_student(student_id)
        if not items:
            return StudentContext.empty()

        total = len(items)
        type_counts: dict[str, int] = {}
        hint_levels: list[int] = []
        session_counts: dict[str, int] = {}
        for item in items:
            q_type = item.get("question_type", "other")
            type_counts[q_type] = type_counts.get(q_type, 0) + 1
            hint_levels.append(int(item.get("hint_level", 1)))
            sid = item.get("session_id", "unknown")
            session_counts[sid] = session_counts.get(sid, 0) + 1

        avg_hint = sum(hint_levels) / len(hint_levels)
        sessions_count = len(session_counts)
        avg_q_per_session = total / sessions_count if sessions_count else 0.0
        primary_type = max(type_counts, key=type_counts.get)

        summary = self._generate_summary(
            total=total,
            type_counts=type_counts,
            avg_hint=avg_hint,
            sessions_count=sessions_count,
            avg_questions_per_session=avg_q_per_session,
            primary_type=primary_type,
        )

        raw = {
            "total_questions": total,
            "question_type_distribution": type_counts,
            "avg_hint_level": round(avg_hint, 2),
            "sessions_count": sessions_count,
            "avg_questions_per_session": round(avg_q_per_session, 1),
            "session_help_frequency": session_counts,
            "summary": summary,
        }
        return StudentContext(
            total_questions=total,
            summary=summary,
            avg_hint_level=round(avg_hint, 2),
            question_type_distribution=type_counts,
            sessions_count=sessions_count,
            raw=raw,
        )
