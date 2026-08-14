"""
Lab Companion — the only student-facing agent.

Constructor injection: takes an `LLMClient` and the active config.
Knowledge-base lookup is performed by the orchestrator and passed in via
`rag_context`, so this agent has zero retrieval dependencies of its own.
"""

from __future__ import annotations

import logging
from typing import Optional

from ..config import SystemConfig
from ..llm import LLMClient

logger = logging.getLogger(__name__)


GUIDANCE_INSTRUCTIONS = {
    "FULL": (
        "Use normal hint-style tutoring. You may explain concepts, walk through "
        "general procedures, and ask clarifying questions. Do NOT write a complete "
        "solution to the student's specific assignment problem; nudge them to "
        "produce the answer themselves."
    ),
    "MODERATE": (
        "Nudge harder toward independence. Prefer asking the student a clarifying "
        "question or pointing them to the relevant section/formula over giving a "
        "direct explanation. Keep the response short."
    ),
    "MINIMAL": (
        "Provide AT MOST ONE short hint, no elaboration. Do not write code. "
        "Do not list steps. One or two sentences. Encourage the student to think."
    ),
    "REJECTED": (
        "Politely decline to answer this specific question. Briefly note that "
        "the student should attempt the problem themselves first, or rephrase "
        "their question in a more conceptual way. Do not provide hints, code, "
        "values, or step-by-step guidance."
    ),
}


SAFE_FALLBACK = (
    "Let me rephrase — what part of the problem are you stuck on? "
    "Tell me what you've tried so far and where it broke down."
)


def _hint_level_descriptor(avg: float) -> str:
    if avg >= 2.5:
        return "tends to need detailed explanations and pointers to documentation"
    if avg >= 1.5:
        return "benefits from moderate hints and explanations of errors"
    return "usually understands with minimal hints"


def _build_system_prompt(
    *,
    learning_summary: str,
    avg_hint_level: float,
    guidance_level: str,
    rag_context: str,
    verifier_feedback: Optional[str] = None,
) -> str:
    guidance_block = GUIDANCE_INSTRUCTIONS.get(
        guidance_level, GUIDANCE_INSTRUCTIONS["FULL"]
    )

    parts = [
        "You are the Lab Companion, a tutoring assistant for Cal Poly's CSC 580 "
        "lab course. You help students work through assignments by giving HINTS, "
        "not answers. Cal Poly's Honor Code requires that all submitted work be "
        "the student's own.",
        "",
        "Hard rules (apply at every guidance level):",
        "  - Never give a complete solution to the student's specific lab problem.",
        "  - Never paste a copy-pasteable code block that solves the assigned task.",
        "  - Never reveal the literal numerical or symbolic answer.",
        "  - You may give tiered hints: (1) check naming/setup, (2) explain the "
        "    error pattern, (3) point to a section/page of the docs.",
        "",
        f"Guidance level for THIS turn: {guidance_level}.",
        f"  -> {guidance_block}",
        "",
        "Student learning context:",
        f"  - Summary: {learning_summary}",
        f"  - Behavior: {_hint_level_descriptor(avg_hint_level)}",
        "",
        "If the question can't be answered from the course resources below, say so.",
        "",
        "--- BEGIN COURSE RESOURCES ---",
        rag_context,
        "--- END COURSE RESOURCES ---",
    ]

    if verifier_feedback:
        parts += [
            "",
            "IMPORTANT — your previous draft was rejected by the integrity reviewer.",
            "Reviewer feedback (incorporate exactly):",
            f"  {verifier_feedback}",
            "Regenerate the response so it satisfies this feedback.",
        ]
    return "\n".join(parts)


class LabCompanion:
    def __init__(self, *, llm: LLMClient, config: SystemConfig) -> None:
        self._llm = llm
        self._config = config

    def respond(
        self,
        *,
        question: str,
        conversation_history: list[dict],
        learning_summary: str,
        avg_hint_level: float,
        guidance_level: str,
        rag_context: str,
        verifier_feedback: Optional[str] = None,
    ) -> str:
        """Generate one draft response. May raise on hard infra errors."""
        system_prompt = _build_system_prompt(
            learning_summary=learning_summary,
            avg_hint_level=avg_hint_level,
            guidance_level=guidance_level,
            rag_context=rag_context,
            verifier_feedback=verifier_feedback,
        )

        keep = self._config.history_keep_turns
        history_trimmed = conversation_history[-keep:] if keep > 0 else []

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history_trimmed)
        messages.append({"role": "user", "content": question})

        return self._llm.complete(messages, temperature=0.4)
