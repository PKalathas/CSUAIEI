from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional

from assessment_agent.models import AssessmentRequest, AssessmentResult
from assessment_agent.agents.orchestrator import assess_submission
from assessment_agent.agents.code_grader import get_available_assignments, load_test_cases
from assessment_agent.interfaces.instructor_copilot import get_review_queue, complete_review
from assessment_agent.interfaces.integrity_guardian import get_anomaly_reports
from assessment_agent import config, persistence
from assessment_agent.config import RESULTS_FILE

router = APIRouter(tags=["assessment"])


def _save_result(result: AssessmentResult) -> None:
    """Persist assessment result to JSON file."""
    persistence.append_json(RESULTS_FILE, result.model_dump())


def _get_results() -> list[dict]:
    return persistence.read_json(RESULTS_FILE)


async def _read_text_upload(
    upload: UploadFile,
    *,
    enforce_size: bool,
    field_name: str,
) -> str:
    """Read an UploadFile as UTF-8 text. Raise HTTP 400 on bad bytes or oversize."""
    content = await upload.read()
    if enforce_size:
        max_bytes = config.MAX_SUBMISSION_SIZE_MB * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(
                400,
                f"{field_name} exceeds {config.MAX_SUBMISSION_SIZE_MB} MB limit",
            )
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, f"{field_name} is not valid UTF-8")


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
        code = await _read_text_upload(code_file, enforce_size=True, field_name="code_file")

    report = None
    if report_file:
        report = await _read_text_upload(report_file, enforce_size=False, field_name="report_file")

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
    target = next((r for r in results if r["submission_id"] == submission_id), None)
    if target is not None:
        manual_weighted = (instructor_score / 10) * 100 * config.MANUAL_REVIEW_WEIGHT
        new_final_score = round(target["automated_score"] + manual_weighted, 2)
        persistence.update_json(
            RESULTS_FILE, "submission_id", submission_id, {"final_score": new_final_score}
        )

    return {"status": "completed", "submission_id": submission_id}


@router.get("/anomalies")
async def list_anomalies(reviewed: bool = None):
    """Get flagged anomaly reports."""
    return get_anomaly_reports(reviewed=reviewed)
