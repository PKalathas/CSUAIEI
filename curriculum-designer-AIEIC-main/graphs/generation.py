"""
LangGraph generation pipeline for the Curriculum Designer.

Flow:
    spec_generator → quiz_generator → rubric_generator → self_review
                                ↑           (conditional retry, max 1)
                         prepare_retry ←────────────────────────────┘

The llm_client is injected via the initial state dict so that MockLLMClient
can be swapped in for tests without any global state.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, TypedDict

from langgraph.graph import StateGraph, END

from models.curriculum import GenerateRequest, QuizQuestion, Rubric

logger = logging.getLogger(__name__)


# ── State ─────────────────────────────────────────────────────────────────────

class GenerationState(TypedDict):
    request: GenerateRequest
    material_content: Optional[str]     # extracted PDF text (may be None)
    agent_instructions: Optional[str]   # instructor instructions (may be None)
    feedback: Optional[str]             # injected on request-changes path
    material_weight: str
    spec_markdown: Optional[str]
    quiz: Optional[List[QuizQuestion]]
    rubric: Optional[Rubric]
    self_review_notes: List[str]
    retry_count: int
    llm_client: Any                     # AzureLLMClient or MockLLMClient


# ── Nodes ─────────────────────────────────────────────────────────────────────

async def spec_generator_node(state: GenerationState) -> dict:
    # Spec-skip pattern: on request-changes path the spec is already set
    if state.get("spec_markdown"):
        logger.info("spec_generator: spec already present, skipping regeneration")
        return {}

    req = state["request"]
    logger.info("spec_generator: generating spec for lab_id=%s", req.lab_id)
    spec = await state["llm_client"].generate_spec(
        title=req.title,
        objectives=req.learning_objectives,
        difficulty=req.difficulty,
        duration_min=req.estimated_duration_min,
        material_content=state.get("material_content"),
        agent_instructions=state.get("agent_instructions"),
    )
    return {"spec_markdown": spec}


async def quiz_generator_node(state: GenerationState) -> dict:
    req = state["request"]
    logger.info("quiz_generator: generating quiz (retry_count=%d)", state.get("retry_count", 0))
    quiz = await state["llm_client"].generate_quiz(
        spec_markdown=state["spec_markdown"],
        objectives=req.learning_objectives,
        material_content=state.get("material_content"),
        agent_instructions=state.get("agent_instructions"),
        feedback=state.get("feedback"),
    )
    return {"quiz": quiz}


async def rubric_generator_node(state: GenerationState) -> dict:
    logger.info("rubric_generator: generating rubric")
    rubric = await state["llm_client"].generate_rubric(
        spec_markdown=state["spec_markdown"],
        quiz=state["quiz"],
        feedback=state.get("feedback"),
    )
    return {"rubric": rubric}


async def self_review_node(state: GenerationState) -> dict:
    req = state["request"]
    logger.info("self_review: running consistency check")
    notes = await state["llm_client"].self_review(
        spec_markdown=state["spec_markdown"],
        quiz=state["quiz"],
        rubric=state["rubric"],
        objectives=req.learning_objectives,
    )
    logger.info("self_review: found %d issue(s)", len(notes))
    return {"self_review_notes": notes}


async def prepare_retry_node(state: GenerationState) -> dict:
    """Join self-review notes into feedback and increment the retry counter."""
    review_notes = "\n".join(state["self_review_notes"])
    original_feedback = state.get("feedback") or ""
    feedback = f"{original_feedback}\n{review_notes}".strip()

    logger.info("prepare_retry: injecting self-review notes as feedback for quiz regeneration")
    return {
        "feedback": feedback,
        "retry_count": state.get("retry_count", 0) + 1,
        "self_review_notes": [],    # clear so next review starts fresh
    }


# ── Conditional edge ──────────────────────────────────────────────────────────

def should_retry(state: GenerationState) -> str:
    if state.get("self_review_notes") and state.get("retry_count", 0) < 1:
        return "prepare_retry"
    return END


# ── Graph factory ─────────────────────────────────────────────────────────────

def build_generation_graph():
    """Build and compile the LangGraph generation pipeline.

    Returns a compiled graph whose ainvoke() accepts a GenerationState dict.
    """
    builder = StateGraph(GenerationState)

    builder.add_node("spec_generator", spec_generator_node)
    builder.add_node("quiz_generator", quiz_generator_node)
    builder.add_node("rubric_generator", rubric_generator_node)
    builder.add_node("self_review", self_review_node)
    builder.add_node("prepare_retry", prepare_retry_node)

    builder.set_entry_point("spec_generator")
    builder.add_edge("spec_generator", "quiz_generator")
    builder.add_edge("quiz_generator", "rubric_generator")
    builder.add_edge("rubric_generator", "self_review")
    builder.add_conditional_edges(
        "self_review",
        should_retry,
        {"prepare_retry": "prepare_retry", END: END},
    )
    builder.add_edge("prepare_retry", "quiz_generator")

    return builder.compile()
