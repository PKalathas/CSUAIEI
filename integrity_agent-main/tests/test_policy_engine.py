"""
Tests for policy_engine.py — classify_question() and ClassificationResult shape.

determine_guidance_level() has been removed. These tests verify:
  - ClassificationResult has concept_tags and no enforcement fields
  - All 5 classifications are returned correctly
  - concept_tags are extracted from LLM JSON
  - Missing concept_tags key defaults to []
  - Malformed JSON propagates as JSONDecodeError
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from models import QuestionClassification
from policy_engine import ClassificationResult, classify_question

SESSION_CONTEXT = {"lab_id": "lab01", "question_count": 3, "violation_count": 0}


def _make_openai_mock(
    classification: str,
    concept_tags: list[str] | None = None,
    confidence: float = 0.95,
) -> MagicMock:
    payload = json.dumps({
        "classification": classification,
        "confidence": confidence,
        "reasoning": "mocked",
        "concept_tags": concept_tags if concept_tags is not None else [],
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


def _make_malformed_mock(raw: str) -> MagicMock:
    mock_msg = MagicMock()
    mock_msg.content = raw
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=mock_response)
    return client


# ---------------------------------------------------------------------------
# ClassificationResult shape — no enforcement fields
# ---------------------------------------------------------------------------

async def test_result_has_no_recommended_guidance_field():
    client = _make_openai_mock("CONCEPTUAL")
    result = await classify_question(
        question_text="What is Thevenin equivalent?",
        conversation_history=[],
        session_context=SESSION_CONTEXT,
        openai_client=client,
        deployment_name="fake-deployment",
    )
    assert not hasattr(result, "recommended_guidance"), (
        "ClassificationResult should not have recommended_guidance"
    )


async def test_result_has_no_student_facing_message_field():
    client = _make_openai_mock("CONCEPTUAL")
    result = await classify_question(
        question_text="What is Thevenin equivalent?",
        conversation_history=[],
        session_context=SESSION_CONTEXT,
        openai_client=client,
        deployment_name="fake-deployment",
    )
    assert not hasattr(result, "student_facing_message"), (
        "ClassificationResult should not have student_facing_message"
    )


async def test_result_has_concept_tags_field():
    client = _make_openai_mock("CONCEPTUAL", concept_tags=["Thevenin equivalent"])
    result = await classify_question(
        question_text="What is Thevenin equivalent?",
        conversation_history=[],
        session_context=SESSION_CONTEXT,
        openai_client=client,
        deployment_name="fake-deployment",
    )
    assert hasattr(result, "concept_tags")
    assert isinstance(result.concept_tags, list)


# ---------------------------------------------------------------------------
# All 5 classification types
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("classification", [
    "CONCEPTUAL",
    "PROCEDURAL",
    "CLARIFICATION",
    "DIRECT_SOLUTION",
    "ANSWER_FARMING",
])
async def test_all_five_classifications_returned(classification):
    client = _make_openai_mock(classification)
    result = await classify_question(
        question_text="test question",
        conversation_history=[],
        session_context=SESSION_CONTEXT,
        openai_client=client,
        deployment_name="fake-deployment",
    )
    assert result.classification == QuestionClassification(classification)
    assert result.confidence == 0.95
    assert result.reasoning == "mocked"


# ---------------------------------------------------------------------------
# concept_tags extraction
# ---------------------------------------------------------------------------

async def test_concept_tags_extracted():
    client = _make_openai_mock("CONCEPTUAL", concept_tags=["BJT biasing", "KVL"])
    result = await classify_question(
        question_text="How does BJT biasing work with KVL?",
        conversation_history=[],
        session_context=SESSION_CONTEXT,
        openai_client=client,
        deployment_name="fake-deployment",
    )
    assert result.concept_tags == ["BJT biasing", "KVL"]


async def test_concept_tags_empty_list_when_provided_empty():
    client = _make_openai_mock("CLARIFICATION", concept_tags=[])
    result = await classify_question(
        question_text="Is R1 the one on the left?",
        conversation_history=[],
        session_context=SESSION_CONTEXT,
        openai_client=client,
        deployment_name="fake-deployment",
    )
    assert result.concept_tags == []


async def test_concept_tags_defaults_to_empty_when_key_absent():
    """LLM response missing concept_tags key entirely should default to []."""
    payload = json.dumps({
        "classification": "CONCEPTUAL",
        "confidence": 0.9,
        "reasoning": "mocked",
        # no concept_tags key
    })
    mock_msg = MagicMock()
    mock_msg.content = payload
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await classify_question(
        question_text="test",
        conversation_history=[],
        session_context=SESSION_CONTEXT,
        openai_client=client,
        deployment_name="fake-deployment",
    )
    assert result.concept_tags == []


# ---------------------------------------------------------------------------
# Malformed JSON propagates
# ---------------------------------------------------------------------------

async def test_malformed_json_raises():
    client = _make_malformed_mock("not valid json {{{")
    with pytest.raises(json.JSONDecodeError):
        await classify_question(
            question_text="test",
            conversation_history=[],
            session_context=SESSION_CONTEXT,
            openai_client=client,
            deployment_name="fake-deployment",
        )
