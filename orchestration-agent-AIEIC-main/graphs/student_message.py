"""
LangGraph StateGraph — student message flow.

Why LangGraph here (and NOT for the dashboard):
  The student message flow is sequential with conditional routing.
  Each node has a clear dependency on the previous one, and branches
  (e.g. policy violation → skip companion, escalate instead) are wired
  here declaratively.

  The dashboard, by contrast, is purely parallel HTTP calls → asyncio.gather.

Graph structure:

  START
    │
    ▼
  load_context        ← GET /participant/context/{student_id}
    │
    ▼
  policy_check        ← POST /validate (Integrity Agent)
    │
    ├── session_escalated=True  → call_companion (returns canned refusal)
    │
    ▼
  call_companion      ← POST /companion/chat  (stateless, full history supplied)
    │
    ▼
  log_interaction     ← POST /participant/log (fire-and-forget)
    │
    ▼
  END

Clients are injected at graph creation time so the graph can be tested
with mock clients without touching this file.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from aieic_shared.clients.companion import LabCompanionClient
from aieic_shared.clients.integrity import IntegrityClient
from aieic_shared.clients.participant import ParticipantClient
from aieic_shared.schemas.companion import ChatMessage, ChatSource
from aieic_shared.schemas.integrity import QuestionClassification
from aieic_shared.schemas.participant import StudentContextResponse

logger = logging.getLogger(__name__)


# ── Graph state ───────────────────────────────────────────────────────────────

class StudentMessageState(TypedDict):
    """
    Full state flowing through the student message graph.

    Inputs (set by the router before invoking):
        student_id, session_id, lab_id, message, conversation_history

    Outputs (populated by graph nodes, read by the router after invocation):
        reply, sources, hint_level, should_escalate, tokens_used
    """
    # ── inputs ──────────────────────────────────────────────────────────────
    student_id: str
    session_id: str
    lab_id: str
    message: str
    conversation_history: list[ChatMessage]

    # ── populated by load_context ────────────────────────────────────────────
    student_context: Optional[StudentContextResponse]

    # ── populated by policy_check ────────────────────────────────────────────
    integrity_flags: list[str]
    policy_blocked: bool                        # True → companion skipped; refusal returned
    integrity_classification: Optional[str]     # QuestionClassification value or None
    violation_detected: bool
    violation_count: int

    # ── populated by call_companion ──────────────────────────────────────────
    reply: str
    sources: list[ChatSource]
    hint_level: int
    should_escalate: bool
    tokens_used: int


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_student_message_graph(
    participant: ParticipantClient,
    companion: LabCompanionClient,
    integrity: IntegrityClient,
):
    """
    Compile and return the student message LangGraph.

    Accepts real or mock clients — callers decide what to inject.
    Call this once at app startup; reuse the compiled graph across requests.
    """

    # ── Node: load_context ────────────────────────────────────────────────────
    async def load_context(state: StudentMessageState) -> dict:
        """
        Fetch the student's aggregated learning profile.

        This summary is injected into the Lab Companion so it can personalise
        its response (e.g. raise hint level for students who've asked many
        questions, be more patient with beginners).

        Failure is non-fatal: the companion still answers, just without context.
        """
        try:
            ctx = await participant.get_student_context(state["student_id"])
            logger.debug(
                f"[load_context] {state['student_id']}: "
                f"{ctx.total_questions} questions, avg_hint={ctx.avg_hint_level:.1f}"
            )
            return {"student_context": ctx}
        except Exception as exc:
            logger.warning(
                f"[load_context] Participant Agent unavailable ({exc}); "
                "continuing without student context."
            )
            return {"student_context": None}

    # ── Node: policy_check ────────────────────────────────────────────────────
    async def policy_check(state: StudentMessageState) -> dict:
        """
        Call POST /validate on the Integrity Agent before forwarding to companion.

        Routing rules (from ValidateQuestionResponse docstring):
          - session_escalated=True  → block companion entirely (3+ violations)
          - violation_detected=True → companion still answers, but classification
                                      is recorded so it can constrain guidance
          - otherwise               → normal companion response
        """
        _clean = {
            "integrity_flags": [],
            "policy_blocked": False,
            "integrity_classification": None,
            "violation_detected": False,
            "violation_count": 0,
        }
        try:
            history = [
                {"role": msg.role, "content": msg.content}
                for msg in state["conversation_history"]
            ]
            result = await integrity.validate(
                student_id=state["student_id"],
                session_id=state["session_id"],
                lab_id=state["lab_id"],
                question_text=state["message"],
                conversation_history=history,
            )
            logger.debug(
                f"[policy_check] {state['student_id']}: "
                f"classification={result.classification}, "
                f"violation={result.violation_detected}, "
                f"escalated={result.session_escalated}"
            )
            return {
                "integrity_flags": [result.violation_type] if result.violation_detected else [],
                "policy_blocked": result.session_escalated,
                "integrity_classification": result.classification,
                "violation_detected": result.violation_detected,
                "violation_count": result.violation_count,
            }
        except Exception as exc:
            logger.warning(
                f"[policy_check] Integrity Agent unavailable ({exc}); allowing through."
            )
            return _clean

    # ── Node: call_companion ──────────────────────────────────────────────────
    async def call_companion(state: StudentMessageState) -> dict:
        """
        Call the Lab Companion with the full conversation context.

        If policy_blocked is True (set by policy_check), skip the real call
        and return a canned refusal.  This is the Phase 2 throttle path.

        Falls back gracefully if the Companion is unavailable — the student
        gets a service-unavailable message rather than a 500 error.
        """
        if state.get("policy_blocked"):
            logger.info(
                f"[call_companion] Skipping — policy blocked for {state['student_id']}"
            )
            return {
                "reply": (
                    "You've reached the AI assistance limit for this period. "
                    "Take a moment to work through the problem independently — "
                    "your instructor is available if you're completely stuck."
                ),
                "sources": [],
                "hint_level": 1,
                "should_escalate": True,
                "tokens_used": 0,
            }

        try:
            ctx = state.get("student_context")
            response = await companion.chat(
                student_id=state["student_id"],
                session_id=state["session_id"],
                message=state["message"],
                lab_id=state["lab_id"],
                conversation_history=state["conversation_history"],
                student_context_summary=ctx.summary if ctx else None,
            )
            logger.debug(
                f"[call_companion] hint_level={response.hint_level}, "
                f"escalate={response.should_escalate}, tokens={response.tokens_used}"
            )
            return {
                "reply": response.reply,
                "sources": response.sources,
                "hint_level": response.hint_level,
                "should_escalate": response.should_escalate,
                "tokens_used": response.tokens_used,
            }
        except Exception as exc:
            logger.error(f"[call_companion] Lab Companion unavailable: {exc}")
            return {
                "reply": (
                    "The tutoring assistant is temporarily unavailable. "
                    "Please try again in a moment, or ask your instructor directly."
                ),
                "sources": [],
                "hint_level": 1,
                "should_escalate": True,
                "tokens_used": 0,
            }

    # ── Node: log_interaction ─────────────────────────────────────────────────
    async def log_interaction(state: StudentMessageState) -> dict:
        """
        Fire-and-forget: persist the interaction to the Participant Agent.

        We use asyncio.create_task so this does NOT block the response.
        Logging failures are swallowed — they must never affect the student.
        """
        async def _log() -> None:
            try:
                await participant.log_interaction(
                    student_id=state["student_id"],
                    session_id=state["session_id"],
                    message=state["message"],
                )
            except Exception as exc:
                logger.warning(f"[log_interaction] Failed to log interaction: {exc}")

        asyncio.create_task(_log())
        return {}

    # ── Wire the graph ────────────────────────────────────────────────────────
    graph = StateGraph(StudentMessageState)

    graph.add_node("load_context",    load_context)
    graph.add_node("policy_check",    policy_check)
    graph.add_node("call_companion",  call_companion)
    graph.add_node("log_interaction", log_interaction)

    graph.add_edge(START,             "load_context")
    graph.add_edge("load_context",    "policy_check")
    graph.add_edge("policy_check",    "call_companion")
    graph.add_edge("call_companion",  "log_interaction")
    graph.add_edge("log_interaction", END)

    return graph.compile()
