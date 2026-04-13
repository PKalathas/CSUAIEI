import logging

from assessment_agent.models import ReportEvaluation, ReportCriterion
from assessment_agent.llm import LLMProvider
from assessment_agent.rubric import AssignmentRubric
from assessment_agent.prompt_loader import load_prompt
from assessment_agent import config

logger = logging.getLogger(__name__)


def _build_criteria_block(rubric: AssignmentRubric) -> str:
    """Build the numbered criteria list from rubric for prompt injection."""
    lines = []
    for i, c in enumerate(rubric.criteria, 1):
        desc = f" - {c.description}" if c.description else ""
        lines.append(f"{i}. **{c.name}**{desc}")
    return "\n".join(lines)


def _build_criteria_json_template(rubric: AssignmentRubric) -> str:
    """Build the JSON example array from rubric criteria names."""
    entries = []
    for c in rubric.criteria:
        entries.append(
            f'    {{"name": "{c.name}", "score": <0-10>, "justification": "<1-2 sentences>"}}'
        )
    return ",\n".join(entries)


async def evaluate_report(
    report_text: str,
    assignment_id: str,
    rubric: AssignmentRubric | None = None,
    provider: LLMProvider | None = None,
) -> ReportEvaluation:
    """Use an LLM to evaluate a student report against a rubric."""
    # Fall back to defaults for backward compatibility
    if rubric is None:
        from assessment_agent.rubric import default_rubric
        rubric = default_rubric()
    if provider is None:
        from assessment_agent.llm import get_llm_provider
        provider = get_llm_provider()

    prompt = load_prompt(
        "report_evaluation",
        assignment_id=assignment_id,
        course_id=config.COURSE_ID,
        grading_guidance=rubric.guidance or "",
        criteria_block=_build_criteria_block(rubric),
        criteria_json_template=_build_criteria_json_template(rubric),
        report_text=report_text[:config.MAX_REPORT_CHARS],
    )

    try:
        result = await provider.complete_json(prompt)
    except Exception:
        logger.warning("Report evaluation failed", exc_info=True)
        return ReportEvaluation(
            llm_reasoning="Failed to parse LLM response for report evaluation."
        )

    criteria = []
    for c in result.get("criteria", []):
        criteria.append(ReportCriterion(
            name=c["name"],
            score=min(max(float(c.get("score", 0)), 0), 10),
            justification=c.get("justification", ""),
        ))

    total = sum(c.score for c in criteria)
    max_total = sum(c.max_score for c in criteria)
    raw_score = (total / max_total * 100) if max_total > 0 else 0

    return ReportEvaluation(
        criteria=criteria,
        raw_score=round(raw_score, 2),
        weighted_score=round(raw_score * config.REPORT_GRADE_WEIGHT, 2),
        llm_reasoning=result.get("reasoning", ""),
    )
