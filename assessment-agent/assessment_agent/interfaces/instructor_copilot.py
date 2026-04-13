from assessment_agent.models import ManualReviewRequest
from assessment_agent.config import REVIEW_QUEUE_FILE
from assessment_agent.persistence import append_json, read_json, update_json


def queue_for_review(review_request: ManualReviewRequest) -> None:
    """
    Add a submission to the instructor's manual review queue.

    POC: Persists to a local JSON file. In production, this would
    call the Instructor Co-pilot agent's API.
    """
    append_json(REVIEW_QUEUE_FILE, review_request.model_dump())


def get_review_queue(status: str | None = None) -> list[dict]:
    """Retrieve the manual review queue, optionally filtered by status."""
    queue = read_json(REVIEW_QUEUE_FILE)
    if status:
        queue = [r for r in queue if r.get("status") == status]
    return queue


def complete_review(submission_id: str, instructor_score: float, notes: str = "") -> bool:
    """Mark a review as completed with the instructor's score."""
    return update_json(
        REVIEW_QUEUE_FILE,
        "submission_id",
        submission_id,
        {
            "status": "completed",
            "instructor_score": instructor_score,
            "instructor_notes": notes,
        },
    )
