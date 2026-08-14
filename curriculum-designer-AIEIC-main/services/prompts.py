"""
Prompt templates for the Curriculum Designer LLM pipeline.

All prompts demand strict JSON output so responses can be parsed directly with
json.loads() + pydantic validation. The helper `_block` renders optional
context sections cleanly (avoids "None" leaking into prompts).
"""

from __future__ import annotations


def _block(label: str, value: str | None, fallback: str = "None provided.") -> str:
    """Render an optional context section."""
    return f"{label}:\n{value if value else fallback}"

def _difficulty_guide() -> str:
    return (
        "Difficulty tier definitions:\n"
        "- basic: Recognition or recall. e.g. 'What is X?', 'Which option describes Y?'\n"
        "- intermediate: Understanding and application. e.g. Why does X happen when Y?', 'What does this code output and why?'\n"
        "- challenge: Implementation, debugging, or design. e.g. 'Write a function that does X given the constraint Y', 'Find the bug in this code and fix it.'"
    )

def _material_weight_instruction(weight: str) ->str:
    if weight == "strict":
        return "Use NOTHING BUT the uploaded material. Do not introduce new concepts that are not included."
    if weight == "expansive":
        return "Use the uploaded material to start off. Add on to it with content that is applicable."
    return "Use the uploaded material as the main reference. You can expand where applicable."

# ── Spec generation ───────────────────────────────────────────────────────────

def build_spec_prompt(
    title: str,
    objectives: list[str],
    difficulty: str,
    duration_min: int,
    material_content: str | None,
    agent_instructions: str | None,
    material_weight: str = "balanced",
) -> tuple[str, str]:
    """Returns (system_prompt, user_content)."""
    system = (
        "You are an expert CS curriculum designer. "
        "Write clear, complete, and well-structured lab specifications in Markdown. "
        "Tailor the content to the difficulty level and learning objectives provided."
    )
    objectives_list = "\n".join(f"- {obj}" for obj in objectives)
    user = f"""Write a complete lab specification in Markdown for a {difficulty} lab.

Title: {title}
Estimated duration: {duration_min} minutes

Learning objectives:
{objectives_list}

{_block("Uploaded lab material (use as primary reference)", material_content)}

{_block("Instructor instructions", agent_instructions)}

The spec must include these sections: Overview, Learning Objectives, Prerequisites, Setup, Tasks, Submission Requirements.
Return ONLY the Markdown text. Do not wrap it in a code block or add any prose before/after."""
    return system, user


# ── Quiz generation ───────────────────────────────────────────────────────────

def build_quiz_prompt(
    spec_markdown: str,
    objectives: list[str],
    material_content: str | None,
    agent_instructions: str | None,
    feedback: str | None = None,
    num_questions: int = 5,
    material_weight: str = "balanced"
) -> tuple[str, str]:
    objectives_list = "\n".join(f"- {obj}" for obj in objectives)
    feedback_block = (
        f"\nInstructor feedback to address in this regeneration:\n{feedback}\n"
        if feedback else ""
    )
    system = (
        "You are an expert CS assessment designer. "
        "Generate quiz questions that accurately assess the stated learning objectives. "
        "Questions must be clear, unambiguous, and span multiple difficulty tiers."
    )
    user = f"""Generate exactly {num_questions} quiz questions for the lab below.
Include at least one question at each difficulty tier: basic, intermediate, challenge.
{_difficulty_guide()}
{feedback_block}
Lab specification:
{spec_markdown}

Learning objectives:
{objectives_list}

{_block("Uploaded lab material (use for factual accuracy)", material_content)}

{_block("Instructor instructions", agent_instructions)}

Return ONLY a JSON array. Each element must match this schema exactly:
[
  {{
    "id": "q1",
    "question": "<question text>",
    "type": "short_answer|multiple_choice|code|essay",
    "expected_answer": "<concise expected answer>",
    "rubric_points": <integer>,
    "difficulty": "basic|intermediate|challenge",
    "learning_objective_ref": "<exact text of the objective this targets>"
  }}
]
Return ONLY the JSON array. No prose, no code fence."""
    return system, user


# ── Rubric generation ─────────────────────────────────────────────────────────

def build_rubric_prompt(
    spec_markdown: str,
    quiz_json: str,
    feedback: str | None = None,
    material_weight: str = "balanced",
) -> tuple[str, str]:
    system = (
        "You are an expert CS grading rubric designer. "
        "Create rubrics that are fair, specific, and aligned with the lab tasks and quiz."
    )
    feedback_block = (
        f"\nInstructor feedback on generated lab materials that need to be revised:\n{feedback}\n"
        if feedback else ""
    )
    user = f"""Generate a grading rubric for the lab below. Include at least 3 criteria.
Criteria should reflect the lab tasks, skills tested, and quiz content.
{_material_weight_instruction(material_weight)}
{feedback_block}
Lab specification:
{spec_markdown}

Quiz questions (for alignment):
{quiz_json}

Return ONLY this JSON object:
{{
  "code_weight": 0.6,
  "report_weight": 0.3,
  "manual_weight": 0.1,
  "criteria": [
    {{"name": "<criterion name>", "weight": <float 0-1>, "description": "<what earns full marks>"}},
    ...
  ]
}}
Return ONLY the JSON object. No prose, no code fence."""
    return system, user


# ── Self-review ───────────────────────────────────────────────────────────────

def build_self_review_prompt(
    spec_markdown: str,
    quiz_json: str,
    rubric_json: str,
    objectives: list[str],
) -> tuple[str, str]:
    objectives_list = "\n".join(f"- {obj}" for obj in objectives)
    system = (
        "You are a quality reviewer for CS lab materials. "
        "Identify internal consistency issues, coverage gaps, and unclear items."
    )
    user = f"""Review the lab materials below for quality issues.

Learning objectives:
{objectives_list}

Lab specification:
{spec_markdown}

Quiz:
{quiz_json}

Rubric:
{rubric_json}

Check for:
1. Quiz questions that do not map to any learning objective
2. Difficulty tiers missing (must have basic, intermediate, and challenge)
3. Rubric criteria that do not align with lab tasks
4. Ambiguous or unclear question wording

Return ONLY a JSON array of strings. Each string is one specific issue found.
Return [] if no issues. No prose, no code fence."""
    return system, user


# ── Check typos ───────────────────────────────────────────────────────────────

def build_check_typos_prompt(
    spec_markdown: str,
    quiz_json: str,
    rubric_json: str,
) -> tuple[str, str]:
    system = (
        "You are a meticulous technical proofreader for CS educational content. "
        "Find all typos, grammatical errors, factual inconsistencies, and ambiguities."
    )
    user = f"""Proofread the following lab materials for errors and issues.

SPEC:
{spec_markdown}

QUIZ:
{quiz_json}

RUBRIC:
{rubric_json}

Return ONLY a JSON array. Each element must match:
[
  {{
    "location": "spec.overview|spec.tasks|Q1|Q2|rubric.criteria[0]|...",
    "type": "typo|inconsistency|ambiguity|factual",
    "suggestion": "<specific correction or improvement>"
  }}
]
Return [] if nothing found. No prose, no code fence."""
    return system, user
