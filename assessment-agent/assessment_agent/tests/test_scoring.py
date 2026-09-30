import json
from pathlib import Path

from fastapi.testclient import TestClient

import assessment_agent.api.routes as routes_mod
from run import app

client = TestClient(app)


def test_manual_review_final_score_88(data_dir: Path, monkeypatch):
    monkeypatch.setattr(
        routes_mod, "RESULTS_FILE", str(data_dir / "assessment_results.json")
    )

    submission_id = "test-sub-1"

    (data_dir / "review_queue.json").write_text(json.dumps([{
        "submission_id": submission_id,
        "student_id": "test_student",
        "assignment_id": "hw1_sorting",
        "automated_score": 80.0,
        "anomaly_flags": [],
        "priority": "normal",
        "status": "pending",
        "instructor_score": None,
        "instructor_notes": None,
    }]))

    (data_dir / "assessment_results.json").write_text(json.dumps([{
        "submission_id": submission_id,
        "student_id": "test_student",
        "assignment_id": "hw1_sorting",
        "automated_score": 80.0,
        "final_score": 0.0,
    }]))

    resp = client.post(
        f"/review-queue/{submission_id}/complete",
        data={"instructor_score": 8.0, "notes": ""},
    )
    assert resp.status_code == 200

    got = client.get(f"/results/{submission_id}").json()
    assert got["final_score"] == 88.0
