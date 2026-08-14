"""
Policy Engine — LLM-based question classification.

One public entry point:
  classify_question() — calls Azure OpenAI to classify a student question
                        and extract concept tags for struggle analysis.
"""

import json
import logging
from dataclasses import dataclass, field

from openai import AsyncAzureOpenAI

from models import QuestionClassification

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Classification system prompt
# ---------------------------------------------------------------------------

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
  Examples: "Can you explain what impedance matching means?",
            "Why does a bypass capacitor reduce noise?",
            "What is the difference between Thevenin and Norton equivalent circuits?"

PROCEDURAL
  Definition: Student asks how to approach or set up a problem type, without asking for
  their specific numerical answer.
  Examples: "What steps do I take to analyze a BJT amplifier in small-signal mode?",
            "How do I generally set up a KVL equation for a mesh?",
            "What MATLAB function would I use to plot a Bode plot?"

CLARIFICATION
  Definition: Student asks about lab instructions, grading criteria, terminology in the
  handout, or logistical aspects of the assignment.
  Examples: "Does 'DC operating point' mean I should treat capacitors as open circuits?",
            "When the lab says 'verify', do I need a mathematical derivation or just simulation?",
            "Is R1 in Figure 2 connected to the non-inverting input?"

DIRECT_SOLUTION
  Definition: Student requests the specific numerical answer, complete derivation,
  finished code, or full circuit solution for their specific lab assignment, even if
  phrased indirectly.
  Key indicators: specific component values from their lab; phrases like "give me",
  "what is the answer", "solve this for me", "complete this", "write this function",
  "show me the full solution", "just tell me the value"; quoting a specific problem
  or figure and asking for the result.

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
5. When in doubt between CONCEPTUAL/PROCEDURAL and DIRECT_SOLUTION/ANSWER_FARMING,
   prefer the non-violation classification unless the evidence is clear.

## Output Format

Respond with ONLY valid JSON. No markdown, no explanation outside the JSON.

{
  "classification": "CONCEPTUAL|PROCEDURAL|CLARIFICATION|DIRECT_SOLUTION|ANSWER_FARMING",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<1-2 sentence explanation of the classification>",
  "concept_tags": ["<topic 1>", "<topic 2>"]
}

concept_tags: A list of 1-3 short technical topic labels identifying the concept(s) the
student is asking about. Use precise technical terms (e.g. "BJT biasing", "KVL mesh analysis",
"op-amp gain", "MATLAB Bode plot", "Thevenin equivalent"). If the question is purely
logistical or administrative, return an empty list.
"""


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    classification: QuestionClassification
    confidence: float
    reasoning: str
    concept_tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM classifier
# ---------------------------------------------------------------------------

async def classify_question(
    question_text: str,
    conversation_history: list[dict],
    session_context: dict,
    openai_client: AsyncAzureOpenAI,
    deployment_name: str,
) -> ClassificationResult:
    """
    Call Azure OpenAI to classify a student question and extract concept tags.

    session_context keys: violation_count, question_count, lab_id
    conversation_history: [{"role": "user"|"assistant", "content": str}, ...]
    """
    history_text = ""
    if conversation_history:
        lines = []
        for turn in conversation_history[-6:]:  # last 3 exchanges
            role = turn.get("role", "unknown").capitalize()
            content = turn.get("content", "")
            lines.append(f"{role}: {content}")
        history_text = "\n".join(lines)
    else:
        history_text = "(no prior conversation)"

    user_content = (
        f"Lab ID: {session_context.get('lab_id', 'unknown')}\n"
        f"Questions asked this session: {session_context.get('question_count', 0)}\n"
        f"Violations this session: {session_context.get('violation_count', 0)}\n\n"
        f"Conversation history:\n{history_text}\n\n"
        f"Student's current question:\n{question_text}"
    )

    response = await openai_client.chat.completions.create(
        model=deployment_name,
        messages=[
            {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_completion_tokens=400,
    )

    raw = response.choices[0].message.content
    parsed = json.loads(raw)

    return ClassificationResult(
        classification=QuestionClassification(parsed["classification"]),
        confidence=float(parsed.get("confidence", 1.0)),
        reasoning=parsed.get("reasoning", ""),
        concept_tags=parsed.get("concept_tags", []),
    )
