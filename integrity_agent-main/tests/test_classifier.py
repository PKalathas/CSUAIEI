import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import RateLimitError

from models import QuestionClassification
from policy_engine import ClassificationResult, classify_question

SESSION_CONTEXT = {"lab_id": "lab01", "question_count": 3, "violation_count": 0}


def _make_openai_mock(
    classification: str,
    concept_tags: list[str] | None = None,
) -> MagicMock:
    payload = json.dumps({
        "classification": classification,
        "confidence": 0.99,
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
# All 5 classification types
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("classification", [
    "CONCEPTUAL",
    "PROCEDURAL",
    "CLARIFICATION",
    "DIRECT_SOLUTION",
    "ANSWER_FARMING",
])
async def test_classify_all_types(classification):
    client = _make_openai_mock(classification)
    result = await classify_question(
        question_text="test question",
        conversation_history=[],
        session_context=SESSION_CONTEXT,
        openai_client=client,
        deployment_name="fake-deployment",
    )
    assert result.classification == QuestionClassification(classification)
    assert result.confidence == 0.99
    assert result.reasoning == "mocked"
    assert result.concept_tags == []


# ---------------------------------------------------------------------------
# concept_tags
# ---------------------------------------------------------------------------

async def test_concept_tags_extracted_by_classifier():
    client = _make_openai_mock("PROCEDURAL", concept_tags=["op-amp gain"])
    result = await classify_question(
        question_text="How do I find op-amp gain?",
        conversation_history=[],
        session_context=SESSION_CONTEXT,
        openai_client=client,
        deployment_name="fake-deployment",
    )
    assert result.concept_tags == ["op-amp gain"]


# ---------------------------------------------------------------------------
# Malformed JSON response
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


# ---------------------------------------------------------------------------
# RateLimitError and generic exception propagation
# ---------------------------------------------------------------------------

async def test_rate_limit_error_propagates():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        side_effect=RateLimitError(
            message="rate limit exceeded",
            response=MagicMock(status_code=429, headers={}),
            body={},
        )
    )
    with pytest.raises(RateLimitError):
        await classify_question(
            question_text="test",
            conversation_history=[],
            session_context=SESSION_CONTEXT,
            openai_client=client,
            deployment_name="fake-deployment",
        )


async def test_generic_exception_propagates():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=ConnectionError("network failure"))
    with pytest.raises(ConnectionError):
        await classify_question(
            question_text="test",
            conversation_history=[],
            session_context=SESSION_CONTEXT,
            openai_client=client,
            deployment_name="fake-deployment",
        )


# ---------------------------------------------------------------------------
# Conversation history trimming — only last 6 turns sent to OpenAI
# ---------------------------------------------------------------------------

async def test_conversation_history_trimmed_to_last_6_turns():
    client = _make_openai_mock("CONCEPTUAL")

    history = [
        {"role": "user", "content": f"question {i}"}
        for i in range(10)  # 10 turns, only last 6 should be sent
    ]

    await classify_question(
        question_text="test",
        conversation_history=history,
        session_context=SESSION_CONTEXT,
        openai_client=client,
        deployment_name="fake-deployment",
    )

    sent_content = client.chat.completions.create.call_args[1]["messages"][1]["content"]

    # Last 6 turns are "question 4" through "question 9"
    for i in range(4, 10):
        assert f"question {i}" in sent_content

    # First 4 turns should have been trimmed
    for i in range(0, 4):
        assert f"question {i}" not in sent_content
