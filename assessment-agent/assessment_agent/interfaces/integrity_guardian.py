from datetime import datetime

from assessment_agent.models import AnomalyReport
from assessment_agent.config import ANOMALY_REPORTS_FILE
from assessment_agent.persistence import append_json, read_json


def report_anomaly(
    submission_id: str,
    student_id: str,
    assignment_id: str,
    anomaly_report: AnomalyReport,
) -> None:
    """
    Report detected anomalies to the Integrity Guardian.

    POC: Persists to a local JSON file. In production, this would
    call the Integrity Guardian agent's API.
    """
    entry = {
        "submission_id": submission_id,
        "student_id": student_id,
        "assignment_id": assignment_id,
        "overall_risk": anomaly_report.overall_risk,
        "flags": [f.model_dump() for f in anomaly_report.flags],
        "recommendation": anomaly_report.recommendation,
        "timestamp": datetime.now().isoformat(),
        "reviewed": False,
    }
    append_json(ANOMALY_REPORTS_FILE, entry)


def get_anomaly_reports(reviewed: bool | None = None) -> list[dict]:
    """Retrieve anomaly reports, optionally filtered by review status."""
    reports = read_json(ANOMALY_REPORTS_FILE)
    if reviewed is not None:
        reports = [r for r in reports if r.get("reviewed") == reviewed]
    return reports
