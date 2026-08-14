"""
Guardian Agent — input + output policy gate.

Constructor injection: takes a `GuardianStore`, an `LLMClient`, and config.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from ..config import SystemConfig
from ..kb import RetrievedDoc, format_context
from ..llm import LLMClient
from ..models import (
    GuidanceLevel,
    QuestionClassification,
    QuestionRecord,
    ValidateResult,
    VerificationRecord,
    VerifyResult,
    ViolationRecord,
    ViolationSeverity,
    ViolationType,
)
from ..policy.engine import (
    ClassificationResult,
    classify_question,
    derive_guidance_level,
    verify_response,
)
from ..store.base import GuardianStore

logger = logging.getLogger(__name__)


class GuardianAgent:
    def __init__(
        self,
        *,
        store: GuardianStore,
        llm: LLMClient,
        config: SystemConfig,
    ) -> None:
        self._store = store
        self._llm = llm
        self._config = config
        self._store.init()

    # -------------------------------------------------------------- lifecycle
    def session_start(
        self,
        *,
        student_id: str,
        session_id: str,
        lab_id: str,
        course_id: str,
    ) -> None:
        started_at = datetime.utcnow().isoformat() + "Z"
        try:
            self._store.create_session(
                {
                    "session_id": session_id,
                    "student_id": student_id,
                    "lab_id": lab_id,
                    "course_id": course_id,
                    "started_at": started_at,
                }
            )
            logger.info("Session started: student=%s session=%s", student_id, session_id)
        except Exception as e:
            # Idempotent: treat duplicates as success.
            if "UNIQUE" in str(e) or "IntegrityError" in type(e).__name__:
                logger.info("Session already exists: %s", session_id)
                return
            logger.error("Failed to create session: %s", e, exc_info=True)
            raise

    def session_end(self, *, student_id: str, session_id: str) -> Optional[dict]:
        session = self._store.get_session(session_id, student_id)
        if session is None:
            logger.warning("session_end: session not found %s", session_id)
            return None

        ended_at = datetime.utcnow().isoformat() + "Z"
        questions = session.get("questions", [])
        classification_distribution = {c.value: 0 for c in QuestionClassification}
        for q in questions:
            cls = q.get("classification")
            if cls in classification_distribution:
                classification_distribution[cls] += 1

        summary = {
            "question_count": session.get("question_count", 0),
            "violation_count": session.get("violation_count", 0),
            "escalated": session.get("escalated", False),
            "classification_distribution": classification_distribution,
        }
        report_id = str(uuid.uuid4())
        self._store.close_session(
            session_id, student_id, ended_at=ended_at, report_id=report_id
        )
        logger.info(
            "Session ended: student=%s session=%s report=%s",
            student_id, session_id, report_id,
        )
        return {"report_id": report_id, "summary": summary}

    # -------------------------------------------------------------- validate
    def validate(
        self,
        *,
        student_id: str,
        session_id: str,
        lab_id: str,
        question_text: str,
        conversation_history: list[dict],
        rag_docs: list[RetrievedDoc] | None = None,
    ) -> ValidateResult:
        session = self._store.get_session(session_id, student_id)
        if session is None:
            raise RuntimeError(f"Session not found: {session_id}")
        if session.get("status") == "closed":
            raise RuntimeError(f"Session already closed: {session_id}")

        question_count = session.get("question_count", 0) + 1
        violation_count = session.get("violation_count", 0)
        session_escalated = bool(session.get("escalated", False))

        rag_context = format_context(rag_docs or [], max_content_chars=800)

        try:
            llm_result: ClassificationResult = classify_question(
                question_text=question_text,
                conversation_history=conversation_history,
                session_context={
                    "lab_id": lab_id,
                    "question_count": question_count,
                    "violation_count": violation_count,
                },
                llm=self._llm,
                rag_context=rag_context if rag_docs else "",
            )
        except Exception as e:
            logger.error("Classifier error (fail-safe applied): %s", e, exc_info=True)
            llm_result = ClassificationResult(
                classification=QuestionClassification.PROCEDURAL,
                confidence=0.0,
                reasoning="Classifier unavailable — fail-safe applied.",
                concept_tags=[],
            )

        classification = llm_result.classification
        if classification == QuestionClassification.DIRECT_SOLUTION:
            is_violation = True
            violation_type: Optional[ViolationType] = ViolationType.DIRECT_SOLUTION_REQUEST
            severity = ViolationSeverity.MAJOR
        elif classification == QuestionClassification.ANSWER_FARMING:
            is_violation = True
            violation_type = ViolationType.ANSWER_FARMING
            severity = ViolationSeverity.MINOR
        else:
            is_violation = False
            violation_type = None
            severity = None

        question_id = str(uuid.uuid4())
        if is_violation and violation_type is not None and severity is not None:
            violation_count += 1
            v_record = ViolationRecord(
                question_id=question_id,
                sequence_number=question_count,
                violation_type=violation_type,
                severity=severity,
                question_text=question_text,
            )
            self._store.insert_violation(session_id, student_id, v_record.model_dump())
            if violation_count >= 3 and not session_escalated:
                session_escalated = True
                logger.critical(
                    "INTEGRITY ESCALATION: student=%s session=%s violations=%d",
                    student_id, session_id, violation_count,
                )

        q_record = QuestionRecord(
            question_id=question_id,
            sequence_number=question_count,
            text=question_text,
            classification=classification,
            violation=is_violation,
            violation_type=violation_type,
            concept_tags=llm_result.concept_tags,
        )
        self._store.insert_question(session_id, student_id, q_record.model_dump())

        self._store.update_session_counters(
            session_id,
            student_id,
            question_count=question_count,
            violation_count=violation_count,
            escalated=session_escalated,
        )

        guidance = derive_guidance_level(
            classification=classification,
            question_count=question_count,
            violation_count=violation_count,
            session_escalated=session_escalated,
        )

        logger.info(
            "validate: student=%s q=%d classification=%s violation=%s guidance=%s",
            student_id, question_count, classification.value,
            violation_type.value if violation_type else "none", guidance.value,
        )

        return ValidateResult(
            classification=classification,
            guidance_level=guidance,
            violation_detected=is_violation,
            violation_type=violation_type,
            violation_count=violation_count,
            question_count=question_count,
            session_escalated=session_escalated,
        )

    # -------------------------------------------------------------- verify
    def verify(
        self,
        *,
        student_id: str,
        session_id: str,
        question_text: str,
        draft_response: str,
        guidance_level: GuidanceLevel,
        classification: Optional[QuestionClassification] = None,
    ) -> VerifyResult:
        session = self._store.get_session(session_id, student_id)
        if session is None:
            raise RuntimeError(f"Session not found: {session_id}")

        try:
            result = verify_response(
                question_text=question_text,
                draft_response=draft_response,
                guidance_level=guidance_level,
                classification=classification,
                llm=self._llm,
            )
            passes = result.passes
            reason = result.reason
            feedback = result.feedback_for_companion
        except Exception as e:
            logger.warning("Verifier error (fail-safe applied): %s", e, exc_info=True)
            passes, reason, feedback = True, "Verifier unavailable; fail-safe applied.", None

        record = VerificationRecord(
            passes=passes,
            reason=reason,
            guidance_level=guidance_level,
            draft_excerpt=draft_response[:500],
        ).model_dump()
        self._store.insert_verification(session_id, student_id, record)

        logger.info(
            "verify: student=%s session=%s passes=%s guidance=%s",
            student_id, session_id, passes, guidance_level.value,
        )
        return VerifyResult(
            passes=passes,
            reason=reason,
            feedback_for_companion=feedback if not passes else None,
        )
