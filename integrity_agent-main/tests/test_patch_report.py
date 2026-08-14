import os
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://fake.openai.azure.com/")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "fake-key")
os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT_NAME", "fake-deployment")
os.environ.setdefault("USE_MEMORY_STORE", "true")
os.environ.setdefault("INTERNAL_API_TOKEN", "demo-token")

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app import app

HEADERS = {"X-Internal-Token": "demo-token", "Content-Type": "application/json"}
BAD_HEADERS = {"X-Internal-Token": "wrong-token", "Content-Type": "application/json"}


def _make_openai_mock():
    payload = json.dumps({
        "classification": "CONCEPTUAL",
        "confidence": 0.99,
        "reasoning": "mocked",
        "concept_tags": [],
    })
    mock_msg = MagicMock()
    mock_msg.content = payload
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=mock_response)
    return client


def _start_session_and_get_report_id(c) -> tuple[str, str]:
    """Helper: start + immediately end a session, return (student_id, report_id)."""
    student_id = "patch-test"
    session_id = str(uuid.uuid4())
    c.post("/session/start", json={
        "student_id": student_id, "session_id": session_id,
        "lab_id": "lab01", "course_id": "EE101",
    }, headers=HEADERS)
    r = c.post("/session/end", json={
        "student_id": student_id, "session_id": session_id,
    }, headers=HEADERS)
    return student_id, r.json()["report_id"]


def test_patch_happy_path():
    with TestClient(app) as c:
        app.state.openai_client = _make_openai_mock()
        student_id, report_id = _start_session_and_get_report_id(c)

        r = c.patch(f"/report/{report_id}", json={
            "student_id": student_id,
            "instructor_notes": {"flagged": True, "note": "test note"},
        }, headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["instructor_notes"] == {"flagged": True, "note": "test note"}

        r = c.get(f"/report/{report_id}", params={"student_id": student_id}, headers=HEADERS)
        assert r.json()["instructor_notes"] == {"flagged": True, "note": "test note"}


def test_patch_overwrites_existing_notes():
    with TestClient(app) as c:
        app.state.openai_client = _make_openai_mock()
        student_id, report_id = _start_session_and_get_report_id(c)

        c.patch(f"/report/{report_id}", json={
            "student_id": student_id,
            "instructor_notes": {"flagged": True, "note": "first"},
        }, headers=HEADERS)

        r = c.patch(f"/report/{report_id}", json={
            "student_id": student_id,
            "instructor_notes": {"flagged": False, "note": "overwritten"},
        }, headers=HEADERS)
        assert r.status_code == 200

        r = c.get(f"/report/{report_id}", params={"student_id": student_id}, headers=HEADERS)
        assert r.json()["instructor_notes"] == {"flagged": False, "note": "overwritten"}


def test_patch_wrong_student_id_returns_404():
    with TestClient(app) as c:
        app.state.openai_client = _make_openai_mock()
        student_id, report_id = _start_session_and_get_report_id(c)

        r = c.patch(f"/report/{report_id}", json={
            "student_id": "different-student",
            "instructor_notes": {"flagged": True},
        }, headers=HEADERS)
        assert r.status_code == 404


def test_patch_nonexistent_report_returns_404():
    with TestClient(app) as c:
        app.state.openai_client = _make_openai_mock()
        r = c.patch("/report/nonexistent-id", json={
            "student_id": "test",
            "instructor_notes": {"flagged": True},
        }, headers=HEADERS)
        assert r.status_code == 404


def test_patch_bad_token_returns_403():
    with TestClient(app) as c:
        app.state.openai_client = _make_openai_mock()
        student_id, report_id = _start_session_and_get_report_id(c)

        r = c.patch(f"/report/{report_id}", json={
            "student_id": student_id,
            "instructor_notes": {"flagged": True},
        }, headers=BAD_HEADERS)
        assert r.status_code == 403
