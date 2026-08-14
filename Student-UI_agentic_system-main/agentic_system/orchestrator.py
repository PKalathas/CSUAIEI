"""
Internal pipeline orchestrator. Not part of the public API — the
embedder uses `agentic_system.LabHarness` instead, which composes this.

Per-turn order:
  1. KB.search(question) → rag_docs + rag_context.
  2. Guardian.validate(question, history, rag_docs) -> guidance_level.
     - classifier receives KB docs so it can apply the KB match rule
       (question semantically targets a lab assignment → DIRECT_SOLUTION).
     - if session_escalated and REJECTED → render escalation; end turn.
     - if guidance_level == REJECTED → render policy refusal; end turn.
  3. LabCompanion.respond(...) → draft.
  4. Guardian.verify(question, draft, guidance_level) → {passes, feedback}.
     - if !passes: re-call respond() with feedback. Up to N retries.
     - on final retry failing: emit safe fallback.
  5. Participant.log() (best-effort).
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Callable, Optional

from .agents import GuardianAgent, LabCompanion, ParticipantAgent
from .agents.lab_companion import SAFE_FALLBACK
from .config import SystemConfig
from .kb import KnowledgeBase, format_context
from .models import (
    GuidanceLevel,
    QuestionClassification,
    SessionState,
    TurnResult,
    ValidateResult,
    VerifyResult,
)

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
        self,
        *,
        config: SystemConfig,
        participant: ParticipantAgent,
        guardian: GuardianAgent,
        companion: LabCompanion,
        knowledge_base: KnowledgeBase,
    ) -> None:
        self._config = config
        self._participant = participant
        self._guardian = guardian
        self._companion = companion
        self._kb = knowledge_base

    # -------------------------------------------------------- lifecycle
    def start_session(self, student_id: Optional[str] = None) -> SessionState:
        session_id = str(uuid.uuid4())
        sid = student_id or self._config.student_id
        student_context = self._participant.get_student_context(sid)
        self._guardian.session_start(
            student_id=sid,
            session_id=session_id,
            lab_id=self._config.lab_id,
            course_id=self._config.course_id,
        )
        logger.info("Session started: %s (student_id=%s)", session_id, sid)
        return SessionState(
            session_id=session_id,
            student_context=student_context,
            conversation_history=[],
            student_id=sid,
        )

    def end_session(self, state: SessionState) -> None:
        self._guardian.session_end(
            student_id=state.student_id or self._config.student_id,
            session_id=state.session_id,
        )
        logger.info("Session ended: %s", state.session_id)

    # -------------------------------------------------------- per-turn
    def handle_turn(
        self,
        state: SessionState,
        question: str,
        *,
        on_step: Optional[Callable[[str, str, str], None]] = None,
    ) -> TurnResult:
        t0 = time.perf_counter()

        # 1. RAG — run before validation so docs inform classification.
        rag_docs: list = []
        try:
            rag_docs = self._kb.search(question, top=self._config.rag_top_n)
            rag_context = format_context(
                rag_docs,
                max_content_chars=self._config.rag_max_content_chars,
            )
        except Exception as e:
            logger.warning("KB.search failed; proceeding without context: %s", e)
            rag_context = format_context([])

        if on_step and self._config.search_enabled:
            on_step(
                "Knowledge Base · Context Retrieval",
                "retrieval",
                _fmt_rag_sources(rag_docs),
            )

        # 2. Validate — passes rag_docs so classifier can apply the KB match rule.
        sid = state.student_id or self._config.student_id
        try:
            validation = self._guardian.validate(
                student_id=sid,
                session_id=state.session_id,
                lab_id=self._config.lab_id,
                question_text=question,
                conversation_history=state.conversation_history,
                rag_docs=rag_docs,
            )
        except Exception as e:
            logger.error("Guardian.validate failed (fail-safe MODERATE): %s", e)
            validation = self._fail_safe_validation()

        if on_step:
            on_step("Guardian · Input Validation", "tool", _fmt_validate(validation))

        # 3. Hard short-circuits.
        if validation.session_escalated and validation.guidance_level == GuidanceLevel.REJECTED:
            return self._refusal_turn(
                state, question, t0, validation, on_step=on_step,
                response=(
                    "I've noticed multiple integrity-flagged questions this session, so "
                    "I won't keep answering. Please review the lab manual, attempt the "
                    "problem yourself, and reach out to your instructor if you're stuck."
                ),
                escalated=True,
            )

        if validation.guidance_level == GuidanceLevel.REJECTED:
            return self._refusal_turn(
                state, question, t0, validation, on_step=on_step,
                response=(
                    "That looks like a request for a direct solution to your "
                    "assignment. I can help you think through the underlying concept "
                    "or point you to the relevant section of the lab manual — what "
                    "specifically is tripping you up?"
                ),
                escalated=False,
            )

        # 4. Draft → verify → retry loop.
        draft, verifier, retries, fallback = self._draft_and_verify(
            state=state,
            question=question,
            validation=validation,
            rag_context=rag_context,
            on_step=on_step,
        )

        # 5. Log + record.
        self._log_turn(state, question, t0)
        self._record_turn(state, question, draft)

        if on_step:
            on_step("Participant · Interaction Logged", "tool", "Interaction recorded to participant store.")

        return TurnResult(
            response=draft,
            guidance_level=validation.guidance_level.value,
            classification=validation.classification.value,
            violation_detected=validation.violation_detected,
            session_escalated=validation.session_escalated,
            verifier_passes=verifier.passes,
            retries=retries,
            fallback=fallback,
            rag_docs_count=len(rag_docs),
            verify_reason=verifier.reason,
            violation_count=validation.violation_count,
        )

    # -------------------------------------------------------- helpers
    def _refusal_turn(
        self,
        state: SessionState,
        question: str,
        t0: float,
        validation: ValidateResult,
        *,
        on_step: Optional[Callable[[str, str, str], None]],
        response: str,
        escalated: bool,
    ) -> TurnResult:
        if on_step:
            on_step("Participant · Interaction Logged", "tool", "Interaction recorded to participant store.")
        self._log_turn(state, question, t0)
        self._record_turn(state, question, response)
        return TurnResult(
            response=response,
            guidance_level=validation.guidance_level.value,
            classification=validation.classification.value,
            violation_detected=validation.violation_detected,
            session_escalated=escalated or validation.session_escalated,
            verifier_passes=True,
            retries=0,
            fallback=False,
            violation_count=validation.violation_count,
        )

    def _draft_and_verify(
        self,
        *,
        state: SessionState,
        question: str,
        validation: ValidateResult,
        rag_context: str,
        on_step: Optional[Callable[[str, str, str], None]] = None,
    ) -> tuple[str, VerifyResult, int, bool]:
        last_feedback: Optional[str] = None
        last_verify = VerifyResult(passes=True, reason=None, feedback_for_companion=None)
        max_retries = self._config.verifier_max_retries

        for attempt in range(max_retries + 1):
            try:
                draft = self._companion.respond(
                    question=question,
                    conversation_history=state.conversation_history,
                    learning_summary=state.student_context.summary,
                    avg_hint_level=state.student_context.avg_hint_level,
                    guidance_level=validation.guidance_level.value,
                    rag_context=rag_context,
                    verifier_feedback=last_feedback,
                )
            except Exception as e:
                logger.error("LabCompanion error on attempt %d: %s", attempt, e)
                return (
                    "Sorry — I hit an error generating a response. "
                    "Could you try rephrasing your question?",
                    last_verify,
                    attempt,
                    True,
                )

            try:
                verify = self._guardian.verify(
                    student_id=state.student_id or self._config.student_id,
                    session_id=state.session_id,
                    question_text=question,
                    draft_response=draft,
                    guidance_level=validation.guidance_level,
                    classification=validation.classification,
                )
            except Exception as e:
                # Per plan: verifier failures fail open — pass the draft.
                logger.warning("Guardian.verify failed (fail-safe pass): %s", e)
                verify = VerifyResult(passes=True, reason="verifier-error", feedback_for_companion=None)
                if on_step:
                    label = f"attempt {attempt + 1}" if attempt > 0 else "first attempt"
                    on_step("Lab Companion · Response Generation", "llm", f"Draft generated ({label}).")
                    on_step("Guardian · Output Verification", "tool", "Passed (verifier error — fail-open).")
                return draft, verify, attempt, False

            last_verify = verify

            if on_step:
                label = f"attempt {attempt + 1}" if attempt > 0 else "first attempt"
                on_step("Lab Companion · Response Generation", "llm", f"Draft generated ({label}).")
                verify_out = (
                    "Response passed output verification."
                    if verify.passes
                    else f"Draft rejected — _{verify.reason or 'no reason given'}_ — retrying."
                )
                on_step("Guardian · Output Verification", "tool", verify_out)

            if verify.passes:
                return draft, verify, attempt, False

            logger.info(
                "Verifier rejected draft (attempt %d/%d): %s",
                attempt + 1, max_retries + 1, verify.reason,
            )
            last_feedback = (
                verify.feedback_for_companion
                or "Your previous draft gave away too much. Provide only a short "
                   "hint or a clarifying question; do not include code that solves "
                   "the task or reveal the answer."
            )

        logger.warning("Verifier exhausted; returning safe fallback.")
        return SAFE_FALLBACK, last_verify, max_retries, True

    def _fail_safe_validation(self) -> ValidateResult:
        return ValidateResult(
            classification=QuestionClassification.PROCEDURAL,
            guidance_level=GuidanceLevel.MODERATE,
            violation_detected=False,
            violation_type=None,
            violation_count=0,
            question_count=0,
            session_escalated=False,
        )

    def _log_turn(self, state: SessionState, question: str, t0: float) -> None:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        try:
            self._participant.log_interaction(
                student_id=state.student_id or self._config.student_id,
                session_id=state.session_id,
                message=question,
                response_time_ms=elapsed_ms,
            )
        except Exception as e:
            logger.warning("Participant log failed: %s", e)

    @staticmethod
    def _record_turn(state: SessionState, question: str, response: str) -> None:
        state.conversation_history.append({"role": "user", "content": question})
        state.conversation_history.append({"role": "assistant", "content": response})


_CLASS_LABEL = {
    "CONCEPTUAL": "Conceptual", "PROCEDURAL": "Procedural",
    "CLARIFICATION": "Clarification", "DIRECT_SOLUTION": "Direct Solution",
    "ANSWER_FARMING": "Answer Farming",
}


def _beautify_source(source: str) -> str:
    return os.path.splitext(source)[0].replace("_", " ").title()


def _fmt_rag_sources(rag_docs: list) -> str:
    if not rag_docs:
        return "No matches found."
    sources = sorted({_beautify_source(d.source) for d in rag_docs})
    bullets = "\n".join(f"- {s}" for s in sources)
    return f"Retrieved **{len(sources)}** source{'s' if len(sources) != 1 else ''}:\n{bullets}"


def _fmt_validate(v: ValidateResult) -> str:
    cls = _CLASS_LABEL.get(v.classification.value, v.classification.value)
    lines = [
        f"**Classification:** {cls}",
        f"**Guidance level:** {v.guidance_level.value}",
        f"**{'Violation detected' if v.violation_detected else 'No violation'}** — session total: {v.violation_count}",
    ]
    if v.session_escalated:
        lines.append("**Session escalated** — integrity threshold reached")
    return "\n".join(lines)
