import logging

from assessment_agent.models import (
    FeedbackReport,
    CodeGradeResult,
    ReportEvaluation,
    AnomalyReport,
    LLMCallRecord,
    ProvenanceCollector,
)
from assessment_agent.llm import LLMProvider
from assessment_agent.rubric import AssignmentRubric
from assessment_agent.prompt_loader import load_prompt_with_hash

logger = logging.getLogger(__name__)


def _format_code_section(code_grade: CodeGradeResult | None) -> str:
    if not code_grade:
        return "No code submission evaluated."

    lines = [f"CODE GRADE: {code_grade.raw_score}/100 ({code_grade.tests_passed}/{code_grade.tests_total} tests passed)"]
    for tr in code_grade.test_results:
        status = "PASS" if tr.passed else "FAIL"
        lines.append(f"  [{status}] {tr.name}: expected '{tr.expected_output}', got '{tr.actual_output}'")
        if tr.error:
            lines.append(f"    Error: {tr.error[:200]}")
    return "\n".join(lines)


def _format_report_section(report_eval: ReportEvaluation | None) -> str:
    if not report_eval:
        return "No report submission evaluated."

    lines = [f"REPORT GRADE: {report_eval.raw_score}/100"]
    for c in report_eval.criteria:
        lines.append(f"  {c.name}: {c.score}/{c.max_score} — {c.justification}")
    return "\n".join(lines)


def _format_anomaly_section(anomaly: AnomalyReport | None) -> str:
    if not anomaly or not anomaly.flags:
        return "No anomalies detected."

    lines = [f"ANOMALY CHECK: Risk level = {anomaly.overall_risk}"]
    for f in anomaly.flags:
        lines.append(f"  [{f.severity.upper()}] {f.flag_type} (confidence: {f.confidence:.0%}): {f.evidence}")
    return "\n".join(lines)


async def generate_feedback(
    student_id: str,
    assignment_id: str,
    automated_score: float,
    code_grade: CodeGradeResult | None,
    report_eval: ReportEvaluation | None,
    anomaly: AnomalyReport | None,
    rubric: AssignmentRubric | None = None,
    provider: LLMProvider | None = None,
    collector: ProvenanceCollector | None = None,
) -> FeedbackReport:
    """Generate personalized feedback using an LLM based on all assessment components."""
    if rubric is None:
        from assessment_agent.rubric import default_rubric
        rubric = default_rubric()
    if provider is None:
        from assessment_agent.llm import get_llm_provider
        provider = get_llm_provider()

    prompt, prompt_hash = load_prompt_with_hash(
        "feedback_generation",
        assignment_id=assignment_id,
        student_id=student_id,
        grading_guidance=rubric.guidance or "",
        code_section=_format_code_section(code_grade),
        report_section=_format_report_section(report_eval),
        anomaly_section=_format_anomaly_section(anomaly),
        automated_score=round(automated_score, 1),
    )

    try:
        result, raw, latency_ms = await provider.complete_with_raw(prompt)
        if collector is not None:
            collector.add_call(LLMCallRecord(
                stage="feedback_generation",
                model_id=provider.model_id,
                prompt_hash=prompt_hash,
                prompt_text=prompt,
                raw_response=raw,
                latency_ms=latency_ms,
            ))
    except Exception:
        logger.warning("Feedback generation failed", exc_info=True)
        if collector is not None:
            collector.add_call(LLMCallRecord(
                stage="feedback_generation",
                model_id=getattr(provider, "model_id", "unknown"),
                prompt_hash=prompt_hash,
                prompt_text=prompt,
                raw_response="",
                latency_ms=0,
                success=False,
                error="Feedback generation failed",
            ))
        return FeedbackReport(summary="Unable to generate detailed feedback.")

    return FeedbackReport(
        summary=result.get("summary", ""),
        strengths=result.get("strengths", []),
        improvements=result.get("improvements", []),
        next_steps=result.get("next_steps", []),
    )
