import json
import os
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional

from assessment_agent.models import AssessmentRequest, AssessmentResult
from assessment_agent.agents.orchestrator import assess_submission
from assessment_agent.agents.code_grader import get_available_assignments, load_test_cases
from assessment_agent.interfaces.instructor_copilot import get_review_queue, complete_review
from assessment_agent.interfaces.integrity_guardian import get_anomaly_reports
from assessment_agent import config
from assessment_agent.config import RESULTS_FILE

router = APIRouter(tags=["assessment"])


def _save_result(result: AssessmentResult) -> None:
    """Persist assessment result to JSON file."""
    results = []
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            results = json.load(f)

    results.append(result.model_dump())

    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)


def _get_results() -> list[dict]:
    if not os.path.exists(RESULTS_FILE):
        return []
    with open(RESULTS_FILE) as f:
        return json.load(f)


@router.post("/submit", response_model=AssessmentResult)
async def submit_assessment(
    student_id: str = Form(...),
    assignment_id: str = Form(...),
    code_file: Optional[UploadFile] = File(None),
    report_file: Optional[UploadFile] = File(None),
):
    """Full assessment submission — code + optional report."""
    if not code_file and not report_file:
        raise HTTPException(400, "At least one of code_file or report_file is required")

    code = None
    if code_file:
        code = (await code_file.read()).decode("utf-8")

    report = None
    if report_file:
        content = await report_file.read()
        filename = report_file.filename or ""
        if filename.endswith(".md") or filename.endswith(".txt"):
            report = content.decode("utf-8")
        else:
            # For other formats, try UTF-8 decode
            report = content.decode("utf-8", errors="replace")

    request = AssessmentRequest(
        student_id=student_id,
        assignment_id=assignment_id,
        code=code,
        report=report,
    )

    result = await assess_submission(request)
    _save_result(result)
    return result


@router.post("/submit-json", response_model=AssessmentResult)
async def submit_assessment_json(request: AssessmentRequest):
    """Submit assessment via JSON body (for Chainlit integration)."""
    if not request.code and not request.report:
        raise HTTPException(400, "At least one of code or report is required")

    result = await assess_submission(request)
    _save_result(result)
    return result


@router.get("/assignments")
async def list_assignments():
    """List available assignments with test cases."""
    return get_available_assignments()


@router.get("/assignments/{assignment_id}/test-cases")
async def get_test_cases(assignment_id: str):
    """Get test case metadata for an assignment (instructor view)."""
    cases = load_test_cases(assignment_id)
    if not cases:
        raise HTTPException(404, f"No test cases found for '{assignment_id}'")
    return [tc.model_dump() for tc in cases]


@router.get("/assignments/{assignment_id}/rubric")
async def get_rubric(assignment_id: str):
    """Get the parsed rubric for an assignment."""
    from assessment_agent.rubric import load_rubric
    rubric = load_rubric(assignment_id)
    return rubric.model_dump()


@router.get("/results")
async def list_results(student_id: str = None, assignment_id: str = None):
    """List assessment results with optional filters."""
    results = _get_results()
    if student_id:
        results = [r for r in results if r["student_id"] == student_id]
    if assignment_id:
        results = [r for r in results if r["assignment_id"] == assignment_id]
    return results


@router.get("/results/{submission_id}")
async def get_result(submission_id: str):
    """Get a specific assessment result."""
    results = _get_results()
    for r in results:
        if r["submission_id"] == submission_id:
            return r
    raise HTTPException(404, f"Submission '{submission_id}' not found")


@router.get("/review-queue")
async def list_review_queue(status: str = None):
    """Get the instructor manual review queue."""
    return get_review_queue(status=status)


@router.post("/review-queue/{submission_id}/complete")
async def complete_manual_review(
    submission_id: str,
    instructor_score: float = Form(...),
    notes: str = Form(""),
):
    """Complete a manual review with instructor score (0-10, weighted to 10%)."""
    if not 0 <= instructor_score <= 10:
        raise HTTPException(400, "instructor_score must be between 0 and 10")

    found = complete_review(submission_id, instructor_score, notes)
    if not found:
        raise HTTPException(404, f"Submission '{submission_id}' not in review queue")

    # Update the final score in results
    results = _get_results()
    for r in results:
        if r["submission_id"] == submission_id:
            manual_weighted = instructor_score * config.MANUAL_REVIEW_WEIGHT * 100
            r["final_score"] = round(r["automated_score"] + manual_weighted, 2)
            break

    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)

    return {"status": "completed", "submission_id": submission_id}


@router.get("/anomalies")
async def list_anomalies(reviewed: bool = None):
    """Get flagged anomaly reports."""
    return get_anomaly_reports(reviewed=reviewed)
