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


def _make_openai_mock(classification: str, concept_tags: list[str] | None = None):
    payload = json.dumps({
        "classification": classification,
        "confidence": 0.99,
        "reasoning": "mocked",
        "concept_tags": concept_tags or [],
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


def test_escalation_on_three_violations():
    with TestClient(app) as c:
        app.state.openai_client = _make_openai_mock(
            "DIRECT_SOLUTION", concept_tags=["circuit analysis"]
        )
        session_id = str(uuid.uuid4())

        r = c.post("/session/start", json={
            "student_id": "test", "session_id": session_id,
            "lab_id": "lab01", "course_id": "EE101",
        }, headers=HEADERS)
        assert r.status_code == 200

        for _ in range(3):
            r = c.post("/validate", json={
                "student_id": "test", "session_id": session_id,
                "lab_id": "lab01", "course_id": "EE101",
                "question_text": "Give me the answer",
                "conversation_history": [],
            }, headers=HEADERS)
            assert r.status_code == 200

        data = r.json()
        # Observational fields still present
        assert data["session_escalated"] is True
        assert data["violation_count"] == 3
        assert data["classification"] == "DIRECT_SOLUTION"
        assert data["violation_detected"] is True
        # No enforcement fields
        assert "approved" not in data
        assert "guidance_level" not in data
        assert "student_message" not in data

        r = c.post("/session/end", json={
            "student_id": "test", "session_id": session_id,
        }, headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["summary"]["final_status"] == "ESCALATED"


def test_validate_response_shape_for_clean_question():
    """Non-violation question returns expected observational fields only."""
    with TestClient(app) as c:
        app.state.openai_client = _make_openai_mock(
            "CONCEPTUAL", concept_tags=["Thevenin equivalent"]
        )
        session_id = str(uuid.uuid4())

        c.post("/session/start", json={
            "student_id": "test", "session_id": session_id,
            "lab_id": "lab01", "course_id": "EE101",
        }, headers=HEADERS)

        r = c.post("/validate", json={
            "student_id": "test", "session_id": session_id,
            "lab_id": "lab01", "course_id": "EE101",
            "question_text": "What is Thevenin equivalent?",
            "conversation_history": [],
        }, headers=HEADERS)
        assert r.status_code == 200
        data = r.json()

        assert data["classification"] == "CONCEPTUAL"
        assert data["violation_detected"] is False
        assert data["violation_type"] is None
        assert data["session_escalated"] is False
        assert data["question_count"] == 1
        assert "approved" not in data
        assert "guidance_level" not in data
        assert "student_message" not in data


def test_validate_rate_limit():
    # UUID-based student_id ensures this test never shares quota with others
    student_id = f"rate-limit-{uuid.uuid4()}"

    with TestClient(app) as c:
        app.state.openai_client = _make_openai_mock("CONCEPTUAL")

        statuses = []
        for _ in range(61):
            r = c.post("/validate", json={
                "student_id": student_id,
                "session_id": "fake-session",
                "lab_id": "lab01",
                "course_id": "EE101",
                "question_text": "test",
                "conversation_history": [],
            }, headers=HEADERS)
            statuses.append(r.status_code)

        # First 60 should not be rate limited (404 — session not found)
        assert all(s != 429 for s in statuses[:60])
        # 61st must be rate limited
        assert statuses[60] == 429
