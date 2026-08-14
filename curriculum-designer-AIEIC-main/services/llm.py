"""
Azure OpenAI wrapper for the Curriculum Designer generation pipeline.

Provides AzureLLMClient (real calls) and MockLLMClient (stub data for dev/test).
Use build_llm_client(settings) as the factory — called from main.py lifespan.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from models.curriculum import QuizQuestion, Rubric, RubricCriterion, TypoIssue
from services.prompts import (
    build_spec_prompt,
    build_quiz_prompt,
    build_rubric_prompt,
    build_self_review_prompt,
    build_check_typos_prompt,
)

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the LLM call fails or returns unparseable output."""


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that some LLMs add despite instructions."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # drop first line (``` or ```json) and last line (```)
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return text.strip()


class AzureLLMClient:

    def __init__(self, settings: "Settings") -> None:
        self._llm = AzureChatOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            azure_deployment=settings.azure_openai_deployment_name,
            api_version=settings.azure_openai_api_version,
            temperature=0.3,
        )

    async def _invoke(self, system_prompt: str, user_content: str) -> str:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ]
        try:
            response = await self._llm.ainvoke(messages)
            raw = response.content
            if isinstance(raw, list):
                raw = " ".join(str(p) for p in raw)
            logger.debug("LLM raw response (first 200 chars): %s", str(raw)[:200])
            return _strip_fences(str(raw))
        except Exception as exc:
            raise LLMError(f"Azure OpenAI call failed: {exc}") from exc

    async def generate_spec(
        self,
        title: str,
        objectives: list[str],
        difficulty: str,
        duration_min: int,
        material_content: str | None,
        agent_instructions: str | None,
        material_weight: str = "balanced",
    ) -> str:
        system, user = build_spec_prompt(
            title, objectives, difficulty, duration_min, material_content, agent_instructions,
            material_weight=material_weight,
        )
        return await self._invoke(system, user)

    async def generate_quiz(
        self,
        spec_markdown: str,
        objectives: list[str],
        material_content: str | None,
        agent_instructions: str | None,
        feedback: str | None = None,
        num_questions: int = 5,
    ) -> list[QuizQuestion]:
        system, user = build_quiz_prompt(
            spec_markdown, objectives, material_content, agent_instructions,
            feedback=feedback, num_questions=num_questions,
        )
        raw = await self._invoke(system, user)
        try:
            data = json.loads(raw)
            return [QuizQuestion(**item) for item in data]
        except Exception as exc:
            raise LLMError(f"Quiz JSON parse failed: {exc}\nRaw: {raw[:500]}") from exc

    async def generate_rubric(
        self,
        spec_markdown: str,
        quiz: list[QuizQuestion],
        feedback: str | None = None,
    ) -> Rubric:
        quiz_json = json.dumps([q.model_dump() for q in quiz], indent=2)
        system, user = build_rubric_prompt(spec_markdown, quiz_json)
        raw = await self._invoke(system, user)
        try:
            data = json.loads(raw)
            return Rubric(**data)
        except Exception as exc:
            raise LLMError(f"Rubric JSON parse failed: {exc}\nRaw: {raw[:500]}") from exc

    async def self_review(
        self,
        spec_markdown: str,
        quiz: list[QuizQuestion],
        rubric: Rubric,
        objectives: list[str],
    ) -> list[str]:
        quiz_json = json.dumps([q.model_dump() for q in quiz], indent=2)
        rubric_json = json.dumps(rubric.model_dump(), indent=2)
        system, user = build_self_review_prompt(spec_markdown, quiz_json, rubric_json, objectives)
        raw = await self._invoke(system, user)
        try:
            result = json.loads(raw)
            return [str(item) for item in result]
        except Exception as exc:
            raise LLMError(f"Self-review JSON parse failed: {exc}\nRaw: {raw[:500]}") from exc

    async def check_typos(
        self,
        spec_markdown: str,
        quiz: list[QuizQuestion],
        rubric: Rubric,
    ) -> list[TypoIssue]:
        quiz_json = json.dumps([q.model_dump() for q in quiz], indent=2)
        rubric_json = json.dumps(rubric.model_dump(), indent=2)
        system, user = build_check_typos_prompt(spec_markdown, quiz_json, rubric_json)
        raw = await self._invoke(system, user)
        try:
            data = json.loads(raw)
            return [TypoIssue(**item) for item in data]
        except Exception as exc:
            raise LLMError(f"Check-typos JSON parse failed: {exc}\nRaw: {raw[:500]}") from exc


class MockLLMClient:
    """Stub client for local development without Azure credentials.

    Activated when LLM_BACKEND=mock in the environment.
    Returns predictable data so all endpoints can be exercised end-to-end.
    """

    async def generate_spec(self, title: str, objectives: list[str], difficulty: str,
                            duration_min: int, material_content: str | None,
                            agent_instructions: str | None) -> str:
        obj_lines = "\n".join(f"- {o}" for o in objectives)
        return (
            f"# Lab: {title}\n\n"
            f"_[Mock] {difficulty} lab, ~{duration_min} min._\n\n"
            f"## Learning Objectives\n{obj_lines}\n\n"
            f"## Setup\n[mock placeholder]\n\n"
            f"## Tasks\n[mock placeholder]\n\n"
            f"## Submission\nSubmit code + report.\n"
        )

    async def generate_quiz(self, spec_markdown: str, objectives: list[str],
                            material_content: str | None, agent_instructions: str | None,
                            feedback: str | None = None, num_questions: int = 5) -> list[QuizQuestion]:
        obj = objectives[0] if objectives else "the topic"
        return [
            QuizQuestion(id="q1", question=f"[Mock] Define a key concept from: {obj}.",
                         type="short_answer", expected_answer="mock answer",
                         rubric_points=10, difficulty="basic", learning_objective_ref=obj),
            QuizQuestion(id="q2", question="[Mock] Explain the intermediate concept.",
                         type="short_answer", expected_answer="mock answer",
                         rubric_points=15, difficulty="intermediate", learning_objective_ref=obj),
            QuizQuestion(id="q3", question="[Mock] Implement the challenge task in pseudocode.",
                         type="code", expected_answer="mock answer",
                         rubric_points=20, difficulty="challenge",
                         learning_objective_ref=objectives[-1] if objectives else obj),
        ]

    async def generate_rubric(self, spec_markdown: str,
                              quiz: list[QuizQuestion],
                              feedback: str | None = None) -> Rubric:
        return Rubric(
            code_weight=0.6, report_weight=0.3, manual_weight=0.1,
            criteria=[
                RubricCriterion(name="Correctness", weight=0.5,
                                description="[Mock] Code passes all tests."),
                RubricCriterion(name="Code quality", weight=0.2,
                                description="[Mock] Readable, idiomatic code."),
                RubricCriterion(name="Report clarity", weight=0.3,
                                description="[Mock] Logically presents approach."),
            ],
        )

    async def self_review(self, spec_markdown: str, quiz: list[QuizQuestion],
                          rubric: Rubric, objectives: list[str]) -> list[str]:
        return []   # mock: no issues, no retry

    async def check_typos(self, spec_markdown: str, quiz: list[QuizQuestion],
                          rubric: Rubric) -> list[TypoIssue]:
        return []   # mock: no issues


def build_llm_client(settings: "Settings") -> AzureLLMClient | MockLLMClient:
    """Factory called from main.py lifespan."""
    if settings.llm_backend.lower() == "mock":
        logger.info("LLM backend: mock (stub data)")
        return MockLLMClient()
    logger.info(
        "LLM backend: Azure OpenAI  endpoint=%s  deployment=%s  api_version=%s",
        settings.azure_openai_endpoint,
        settings.azure_openai_deployment_name,
        settings.azure_openai_api_version,
    )
    return AzureLLMClient(settings)
