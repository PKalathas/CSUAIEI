"""
Student-facing router.

All endpoints are prefixed /orchestrator/student/*.

The frontend (or the student chat UI) calls these endpoints.
The router pulls clients and graph from app.state, which is populated
during the FastAPI lifespan in main.py.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from pydantic import BaseModel

from aieic_shared.schemas.assessment import AssessmentResult
from aieic_shared.schemas.orchestrator import (
    StudentMessageRequest,
    StudentMessageResponse,
    StudentSubmitRequest,
)

router = APIRouter(prefix="/orchestrator/student", tags=["student"])
logger = logging.getLogger(__name__)


class EndStudentSessionRequest(BaseModel):
    student_id: str
    session_id: str

# ── Dependency helpers ────────────────────────────────────────────────────────
# We read from app.state instead of using FastAPI Depends() so that
# the clients are shared (one httpx.AsyncClient for the whole process).

def _graph(request: Request):
    return request.app.state.student_message_graph

def _sessions(request: Request):
    return request.app.state.session_store

def _assessment(request: Request):
    return request.app.state.assessment

def _integrity(request: Request):
    return request.app.state.integrity

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/message", response_model=StudentMessageResponse)
async def student_message(body: StudentMessageRequest, request: Request):
    """
    Student sends a message to the Lab Companion.

    Orchestrator coordinates:
      1. Get or create session (tracks conversation_history across turns)
      2. Run LangGraph: load_context → policy_check → call_companion → log_interaction
      3. Persist new turn to session
      4. Return reply + metadata to frontend

    The Lab Companion itself is stateless — conversation_history is stored
    here in the session and injected on each call.
    """
    session_store = _sessions(request)
    graph         = _graph(request)

    # Step 1: resolve session
    session, created_new = session_store.get_or_create(
        student_id=body.student_id,
        lab_id=body.lab_id,
        session_id=body.session_id,
    )
    # If this is a brand-new orchestrator session, initialize the
    # corresponding Integrity session before running the graph.
    if created_new:
        integrity = _integrity(request)
        try:
            await integrity.start_session(
                student_id=body.student_id,
                session_id=session.session_id,
                lab_id=body.lab_id,
                course_id="CSC580",
            )
        except Exception as exc:
            logger.error(f"[student_message] Failed to start Integrity session: {exc}")
            raise HTTPException(
                status_code=502,
                detail="Integrity Agent unavailable during session start",
            )

    # Step 2: run graph
    initial_state = {
        "student_id":           body.student_id,
        "session_id":           session.session_id,
        "lab_id":               body.lab_id,
        "message":              body.message,
        "conversation_history": list(session.conversation_history),  # snapshot
        # Fields populated by nodes — default values required by TypedDict
        "student_context":          None,
        "integrity_flags":          [],
        "policy_blocked":           False,
        "integrity_classification": None,
        "violation_detected":       False,
        "violation_count":          0,
        "reply":                    "",
        "sources":          [],
        "hint_level":       1,
        "should_escalate":  False,
        "tokens_used":      0,
    }

    try:
        final_state = await graph.ainvoke(initial_state)
    except Exception as exc:
        logger.error(f"[student_message] Graph invocation failed: {exc}")
        raise HTTPException(status_code=500, detail="Orchestrator internal error")

    # Step 3: update session history with this completed turn
    session.add_turn(
        user_message=body.message,
        assistant_reply=final_state["reply"],
    )

    # Step 4: return
    return StudentMessageResponse(
        session_id=session.session_id,
        reply=final_state["reply"],
        sources=final_state["sources"],
        hint_level=final_state["hint_level"],
        tokens_used=final_state["tokens_used"],
    )


@router.post("/session/end")
async def end_student_session(body: EndStudentSessionRequest, request: Request):
    """
    End a student session.

    This closes the corresponding Integrity session and removes the local
    orchestrator session from the in-memory store.
    """
    session_store = _sessions(request)
    integrity = _integrity(request)

    session = session_store.get(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.student_id != body.student_id:
        raise HTTPException(status_code=403, detail="Session does not belong to student")

    try:
        result = await integrity.end_session(
            student_id=body.student_id,
            session_id=body.session_id,
        )
    except Exception as exc:
        logger.error(f"[end_student_session] Failed to end Integrity session: {exc}")
        raise HTTPException(
            status_code=502,
            detail="Integrity Agent unavailable during session end",
        )

    session_store.delete(body.session_id)

    return {
        "ok": True,
        "session_id": body.session_id,
        "integrity_report_id": result.report_id,
        "summary": result.summary,
    }


@router.post("/submit", response_model=AssessmentResult)
async def student_submit(body: StudentSubmitRequest, request: Request):
    """
    Student submits final lab work (code + report).

    Orchestrator forwards to the Assessment Agent and returns the result.
    If the submission is flagged as high-risk by the anomaly detector,
    it is automatically routed to the instructor review queue by the
    Assessment Agent itself.
    """
    assessment = _assessment(request)
    try:
        result = await assessment.submit(
            student_id=body.student_id,
            assignment_id=body.assignment_id,
            code=body.code,
            report=body.report,
        )
        return result
    except Exception as exc:
        logger.error(f"[student_submit] Assessment Agent failed: {exc}")
        raise HTTPException(status_code=502, detail="Assessment Agent unavailable")
