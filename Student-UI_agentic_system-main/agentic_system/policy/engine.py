"""
Policy engine — synchronous LLM-based question classification AND
response verification.

Two pure functions and one pure mapping:
  classify_question()    — input gate (verbatim system prompt from the reference impl)
  verify_response()      — output gate (NEW in v1)
  derive_guidance_level() — pure mapping from classification + counters → guidance.

LLM calls go through whatever `LLMClient` the caller passes in. No
client construction here — the agents own that, and the LLM provider is
hidden behind the `LLMClient` protocol.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from ..llm import LLMClient
from ..models import GuidanceLevel, QuestionClassification

logger = logging.getLogger(__name__)


# --------------------------------------------------------------- prompts
CLASSIFICATION_SYSTEM_PROMPT = """You are an academic integrity classifier for Cal Poly's STEM lab courses.
Your job is to determine what type of question a student is asking so that it can be
logged and analyzed for academic integrity patterns.

## Cal Poly Academic Integrity Context
Cal Poly's Honor Code requires that all submitted work be the student's own. In lab courses,
students must demonstrate genuine understanding by deriving their own solutions. Receiving
complete solutions, step-by-step worked answers, or code that directly solves an assignment
problem — even from an AI — constitutes a violation of the Honor Code.

## Classification Categories

Classify the question into exactly ONE of the following:

CONCEPTUAL
  Definition: Student seeks to understand a principle, theory, formula, or concept.

PROCEDURAL
  Definition: Student asks how to approach or set up a problem type, without asking for
  their specific numerical answer.

CLARIFICATION
  Definition: Student asks about lab instructions, grading criteria, terminology in the
  handout, or logistical aspects of the assignment.

DIRECT_SOLUTION
  Definition: Student requests the specific numerical answer, complete derivation,
  finished code, or full circuit solution for their specific lab assignment, even if
  phrased indirectly.

ANSWER_FARMING
  Definition: A sequence of incrementally specific questions that together would
  constitute solving the lab step-by-step without genuine student effort. A single
  question may appear benign, but in the context of the conversation history it
  reveals a pattern of extracting a complete solution piece by piece.

## Decision Rules

1. Read the current question carefully.
2. Review the conversation history for patterns.
3. If the question contains specific numerical values, component names, or an exact
   problem statement from the lab COMBINED with a request to solve/compute/find:
   classify as DIRECT_SOLUTION regardless of phrasing.
4. If the conversation history shows 3 or more questions that together are solving
   one lab problem step-by-step: classify the current question as ANSWER_FARMING
   even if in isolation it looks PROCEDURAL.
5. **KB match rule**: If lab material excerpts are provided and the student's question
   is semantically asking you to solve, complete, derive, compute, or answer any specific
   problem, task, circuit, exercise, or coding challenge that appears in those excerpts —
   classify as DIRECT_SOLUTION. This applies even when the question is phrased as
   "how do I...", "can you walk me through...", or "explain how to..." if the target
   is clearly a specific graded task from the lab material.
   Counter-examples that are NOT DIRECT_SOLUTION under this rule: asking what a concept
   means, asking about a formula in the abstract, or asking for debugging help on code
   the student wrote themselves.
6. When in doubt between CONCEPTUAL/PROCEDURAL and DIRECT_SOLUTION/ANSWER_FARMING,
   prefer the non-violation classification unless the evidence is clear.

## Output Format

Respond with ONLY valid JSON:

{
  "classification": "CONCEPTUAL|PROCEDURAL|CLARIFICATION|DIRECT_SOLUTION|ANSWER_FARMING",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<1-2 sentence explanation>",
  "concept_tags": ["<topic 1>", "<topic 2>"]
}
"""


VERIFICATION_SYSTEM_PROMPT = """You are an academic integrity reviewer for Cal Poly's STEM lab tutoring AI.

A student asked a question and the tutoring AI ("Lab Companion") drafted a response.
Your job is to decide whether the draft is an appropriate **hint-style** response, or
whether it gives away the answer in a way that would undermine the student's learning
or violate Cal Poly's Honor Code.

## What counts as giving away the answer
- A complete code block that directly solves the assigned task (more than a small snippet
  illustrating syntax or an isolated technique).
- The exact numerical, symbolic, or logical answer to a specific lab problem.
- A full step-by-step derivation that leaves no work for the student.
- Copy-pasteable solutions to homework / lab / exam problems.

## What is acceptable
- Conceptual explanations of underlying principles.
- Pointers to which technique, formula, page of the manual, or section of the textbook applies.
- Tiered hints (Level 1: "check variable naming"; Level 2: "this error usually means…";
  Level 3: "see example on page X").
- Asking clarifying questions back to the student.
- Tiny illustrative snippets (a single line of syntax) when the student's question
  is genuinely about syntax — not the assignment.

## Guidance level for THIS turn
- FULL:     Normal hint-style tutoring. Apply the standard policy above.
- MODERATE: Nudge harder toward independence — a draft that would pass under FULL may
            still fail here if it's overly directive.
- MINIMAL:  At most one short hint, no elaboration. Long drafts fail.
- REJECTED: This question should not have been answered at all. Any substantive draft fails.

## Output format

Respond with ONLY valid JSON:

{
  "passes": true | false,
  "confidence": <float 0.0-1.0>,
  "reason": "<1-2 sentence explanation of the decision>",
  "feedback_for_companion": "<if passes=false: a 1-3 sentence instruction the companion
                             should follow when regenerating, telling it WHAT to remove
                             and WHAT kind of hint to give instead. If passes=true, omit
                             or empty string.>"
}
"""


# --------------------------------------------------------------- result shapes
@dataclass
class ClassificationResult:
    classification: QuestionClassification
    confidence: float
    reasoning: str
    concept_tags: list[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    passes: bool
    confidence: float
    reason: str
    feedback_for_companion: Optional[str] = None


# --------------------------------------------------------------- guidance
def derive_guidance_level(
    classification: QuestionClassification,
    question_count: int,
    violation_count: int,
    session_escalated: bool,
) -> GuidanceLevel:
    """
    Pure mapping (classification, counters, escalation) -> guidance level.

      - Hard block (REJECTED) on DIRECT_SOLUTION or after escalation.
      - Throttle: degrade after Q12, MINIMAL at Q14-15, REJECT at Q16+.
      - ANSWER_FARMING -> MINIMAL.
    """
    if session_escalated:
        return GuidanceLevel.REJECTED
    if classification == QuestionClassification.DIRECT_SOLUTION:
        return GuidanceLevel.REJECTED
    if classification == QuestionClassification.ANSWER_FARMING:
        return GuidanceLevel.MINIMAL

    if question_count >= 16:
        return GuidanceLevel.REJECTED
    if question_count >= 14:
        return GuidanceLevel.MINIMAL
    if question_count >= 12 or violation_count >= 1:
        return GuidanceLevel.MODERATE
    return GuidanceLevel.FULL


# --------------------------------------------------------------- LLM calls
def classify_question(
    question_text: str,
    conversation_history: list[dict],
    session_context: dict,
    llm: LLMClient,
    rag_context: str = "",
) -> ClassificationResult:
    history_text = (
        "\n".join(
            f"{(turn.get('role') or 'unknown').capitalize()}: {turn.get('content', '')}"
            for turn in conversation_history[-6:]
        )
        if conversation_history
        else "(no prior conversation)"
    )

    lab_material_block = (
        f"\nLab material retrieved (apply KB match rule #5):\n---\n{rag_context}\n---\n"
        if rag_context
        else ""
    )

    user_content = (
        f"Lab ID: {session_context.get('lab_id', 'unknown')}\n"
        f"Questions asked this session: {session_context.get('question_count', 0)}\n"
        f"Violations this session: {session_context.get('violation_count', 0)}\n"
        f"{lab_material_block}\n"
        f"Conversation history:\n{history_text}\n\n"
        f"Student's current question:\n{question_text}"
    )

    raw = llm.complete(
        [
            {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.0,
        max_tokens=400,
        json_mode=True,
    )
    parsed = json.loads(raw)
    return ClassificationResult(
        classification=QuestionClassification(parsed["classification"]),
        confidence=float(parsed.get("confidence", 1.0)),
        reasoning=parsed.get("reasoning", ""),
        concept_tags=parsed.get("concept_tags", []),
    )


def verify_response(
    question_text: str,
    draft_response: str,
    guidance_level: GuidanceLevel,
    classification: Optional[QuestionClassification],
    llm: LLMClient,
) -> VerificationResult:
    user_content = (
        f"Guidance level for this turn: {guidance_level.value}\n"
        f"Question classification: "
        f"{classification.value if classification else 'UNKNOWN'}\n\n"
        f"Student's question:\n{question_text}\n\n"
        f"Lab Companion's draft response:\n---\n{draft_response}\n---\n\n"
        "Decide: does the draft give away the answer (per the rules above), "
        "or is it an appropriate hint?"
    )

    raw = llm.complete(
        [
            {"role": "system", "content": VERIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.0,
        max_tokens=400,
        json_mode=True,
    )
    parsed = json.loads(raw)
    return VerificationResult(
        passes=bool(parsed.get("passes", True)),
        confidence=float(parsed.get("confidence", 1.0)),
        reason=parsed.get("reason", ""),
        feedback_for_companion=parsed.get("feedback_for_companion") or None,
    )
