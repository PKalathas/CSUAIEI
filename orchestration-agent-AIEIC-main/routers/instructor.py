"""
Instructor-facing router.

All endpoints are prefixed /orchestrator/instructor/*.

Maps directly to the four Figma dashboard tabs + sidebar AI actions.
See INTERFACE_CONTRACT.md §Frontend → Orchestrator Mapping for the full table.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from aieic_shared.schemas.curriculum import CurriculumMaterial, TypoCheckResponse
from aieic_shared.schemas.orchestrator import DashboardResponse, InstructorApprovalRequest

router = APIRouter(prefix="/orchestrator/instructor", tags=["instructor"])
logger = logging.getLogger(__name__)


# ── Dependency helpers ────────────────────────────────────────────────────────

def _dashboard(request: Request):
    return request.app.state.dashboard_service

def _curriculum(request: Request):
    return request.app.state.curriculum

def _assessment(request: Request):
    return request.app.state.assessment


# ── Request bodies not already in aieic-shared ────────────────────────────────

class RequestChangesBody(BaseModel):
    lab_id: str
    feedback: str
    requested_by: str

class GenerateQuizBody(BaseModel):
    lab_id: str
    course_id: str = "csc580"
    title: str = ""
    learning_objectives: list[str] = []
    instructor_id: str = "instructor"

class CheckTyposBody(BaseModel):
    lab_id: str

class CompleteReviewBody(BaseModel):
    instructor_score: float
    notes: str = ""


# ── Tab 1: Material Preview ───────────────────────────────────────────────────

@router.get("/dashboard/{lab_id}", response_model=DashboardResponse)
async def get_dashboard(
    lab_id: str,
    request: Request,
    tab: Optional[str] = Query(
        default=None,
        description="material | activity | grades | stats  (omit = all tabs)",
    ),
):
    """
    Unified dashboard payload — populates all four Figma tabs in one call.

    The Orchestrator calls Curriculum Designer, Participant Agent, and
    Assessment Agent in parallel, then assembles the response.

    Use `?tab=activity` to refresh only the Student Activity tab cheaply.
    """
    try:
        return await _dashboard(request).build(lab_id=lab_id, tab=tab)
    except Exception as exc:
        logger.error(f"[dashboard] Build failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to build dashboard")


@router.post("/material/approve", response_model=CurriculumMaterial)
async def approve_material(body: InstructorApprovalRequest, request: Request):
    """
    Instructor clicks "Approve" in the Material Preview tab.
    Forwards to Curriculum Designer → status becomes 'approved'.
    """
    try:
        return await _curriculum(request).approve(
            lab_id=body.lab_id,
            approved_by=body.approved_by,
            notes=body.notes,
        )
    except Exception as exc:
        logger.error(f"[approve_material] {exc}")
        raise HTTPException(status_code=502, detail="Curriculum Designer unavailable")


@router.post("/material/request-changes", response_model=CurriculumMaterial)
async def request_material_changes(body: RequestChangesBody, request: Request):
    """
    Instructor clicks "Request Changes" — triggers regeneration.
    Status moves back to 'pending'.
    """
    try:
        return await _curriculum(request).request_changes(
            lab_id=body.lab_id,
            feedback=body.feedback,
            requested_by=body.requested_by,
        )
    except Exception as exc:
        logger.error(f"[request_changes] {exc}")
        raise HTTPException(status_code=502, detail="Curriculum Designer unavailable")


# ── Sidebar AI Actions ────────────────────────────────────────────────────────

@router.post("/material/generate-quiz", response_model=CurriculumMaterial)
async def generate_quiz(body: GenerateQuizBody, request: Request):
    """
    Sidebar AI action: "Generate Quiz".
    Calls Curriculum Designer to generate a full lab from learning objectives.
    """
    try:
        return await _curriculum(request).generate(
            course_id=body.course_id,
            lab_id=body.lab_id,
            title=body.title,
            learning_objectives=body.learning_objectives,
            instructor_id=body.instructor_id,
        )
    except Exception as exc:
        logger.error(f"[generate_quiz] {exc}")
        raise HTTPException(status_code=502, detail="Curriculum Designer unavailable")


@router.post("/material/check-typos", response_model=TypoCheckResponse)
async def check_typos(body: CheckTyposBody, request: Request):
    """Sidebar AI action: "Check for Typos & Errors"."""
    try:
        return await _curriculum(request).check_typos(lab_id=body.lab_id)
    except Exception as exc:
        logger.error(f"[check_typos] {exc}")
        raise HTTPException(status_code=502, detail="Curriculum Designer unavailable")


# ── Tab 3: Graded Submissions — manual review ─────────────────────────────────

@router.post("/review/{submission_id}/complete")
async def complete_review(
    submission_id: str,
    body: CompleteReviewBody,
    request: Request,
):
    """
    Instructor completes a manual review of a flagged / pending submission.
    Forwards to Assessment Agent's review queue.
    """
    try:
        return await _assessment(request).complete_review(
            submission_id=submission_id,
            instructor_score=body.instructor_score,
            notes=body.notes,
        )
    except Exception as exc:
        logger.error(f"[complete_review] {exc}")
        raise HTTPException(status_code=502, detail="Assessment Agent unavailable")


@router.get("/submission/{submission_id}")
async def get_submission(submission_id: str, request: Request):
    """Get full detail for a single submission (for instructor review modal)."""
    try:
        return await _assessment(request).get_result(submission_id)
    except Exception as exc:
        logger.error(f"[get_submission] {exc}")
        raise HTTPException(status_code=502, detail="Assessment Agent unavailable")


@router.get("/grades/csv")
async def download_grades_csv(
    lab_id: str = Query(...),
    request: Request = None,
):
    """
    Download all grades as CSV.

    TODO: stream the CSV rather than loading all results into memory.
    For v0.1, this is acceptable given class sizes (~35 students).
    """
    import csv
    import io
    from fastapi.responses import StreamingResponse

    assessment = _assessment(request)
    try:
        results = await assessment.list_results(assignment_id=lab_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Assessment Agent unavailable")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["student_id", "score", "status", "feedback"])
    for r in results:
        score = r.final_score if r.final_score is not None else r.automated_score
        writer.writerow([
            r.student_id,
            score,
            r.status,
            r.feedback.summary if r.feedback else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=grades_{lab_id}.csv"},
    )
