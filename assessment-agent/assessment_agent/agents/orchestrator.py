from assessment_agent.models import (
    AssessmentResult,
    AssessmentRequest,
    SubmissionType,
    ManualReviewRequest,
)
import logging

from assessment_agent.agents.code_grader import grade_code
from assessment_agent.agents.report_evaluator import evaluate_report
from assessment_agent.agents.anomaly_detector import detect_anomalies
from assessment_agent.agents.feedback_generator import generate_feedback
from assessment_agent.interfaces.integrity_guardian import report_anomaly
from assessment_agent.interfaces.instructor_copilot import queue_for_review
from assessment_agent.llm import get_llm_provider, LLMProvider
from assessment_agent.rubric import load_rubric, AssignmentRubric
from assessment_agent.prompt_loader import load_prompt
from assessment_agent import config

logger = logging.getLogger(__name__)


async def assess_submission(request: AssessmentRequest) -> AssessmentResult:
    """
    Main orchestrator: runs the full agentic assessment pipeline.

    The orchestrator reasons about each step's results to make decisions
    about subsequent steps -- this is what makes it agentic rather than
    a fixed pipeline.
    """
    # Load rubric and LLM provider for this assignment
    rubric = load_rubric(request.assignment_id)
    provider = get_llm_provider()

    # Determine submission type
    if request.submission_type:
        sub_type = request.submission_type
    elif request.code and request.report:
        sub_type = SubmissionType.FULL
    elif request.code:
        sub_type = SubmissionType.CODE_ONLY
    else:
        sub_type = SubmissionType.REPORT_ONLY

    result = AssessmentResult(
        student_id=request.student_id,
        assignment_id=request.assignment_id,
        submission_type=sub_type,
    )

    # Step 1: Code Grading (60%)
    code_grade = None
    if request.code and sub_type in (SubmissionType.CODE_ONLY, SubmissionType.FULL):
        code_grade = await grade_code(request.code, request.assignment_id, rubric=rubric, provider=provider)
        result.code_grade = code_grade

    # Step 2: Report Evaluation (30%)
    report_eval = None
    if request.report and sub_type in (SubmissionType.REPORT_ONLY, SubmissionType.FULL):
        report_eval = await evaluate_report(
            request.report, request.assignment_id,
            rubric=rubric, provider=provider,
        )
        result.report_evaluation = report_eval

    # Step 3: Anomaly Detection
    anomaly = None
    if request.code:
        anomaly = await detect_anomalies(
            request.code, student_id=request.student_id,
            rubric=rubric, provider=provider,
        )
        result.anomaly_report = anomaly

    # Step 4: Compute automated score
    automated_score = 0.0
    if code_grade:
        automated_score += code_grade.weighted_score
    if report_eval:
        automated_score += report_eval.weighted_score
    result.automated_score = round(automated_score, 2)

    # Step 5: Orchestrator reasoning
    code_summary = f"{code_grade.raw_score}/100 ({code_grade.tests_passed}/{code_grade.tests_total} passed)" if code_grade else "N/A"
    report_summary = f"{report_eval.raw_score}/100" if report_eval else "N/A"
    anomaly_summary = f"Risk: {anomaly.overall_risk}, {len(anomaly.flags)} flags" if anomaly else "N/A"

    reasoning_prompt = load_prompt(
        "orchestrator_reasoning",
        assignment_id=request.assignment_id,
        course_id=config.COURSE_ID,
        grading_guidance=rubric.guidance or "",
        student_id=request.student_id,
        code_summary=code_summary,
        report_summary=report_summary,
        anomaly_summary=anomaly_summary,
        automated_score=round(automated_score, 1),
    )

    try:
        reasoning = await provider.complete_json(reasoning_prompt)
    except Exception:
        logger.warning("Orchestrator reasoning failed, using defaults", exc_info=True)
        reasoning = {
            "reasoning": "Unable to generate orchestrator reasoning.",
            "score_adjustment": 0,
            "review_priority": "normal",
            "instructor_notes": "",
        }

    # Apply score adjustment if the orchestrator recommends it
    adjustment = float(reasoning.get("score_adjustment", 0))
    result.automated_score = round(max(0, min(90, automated_score + adjustment)), 2)
    result.agent_reasoning = reasoning.get("reasoning", "")

    # --- Step 6: Generate personalized feedback ---
    feedback = await generate_feedback(
        student_id=request.student_id,
        assignment_id=request.assignment_id,
        automated_score=result.automated_score,
        code_grade=code_grade,
        report_eval=report_eval,
        anomaly=anomaly,
        rubric=rubric,
        provider=provider,
    )
    result.feedback = feedback

    # --- Step 7: Queue for manual review ---
    review_priority = reasoning.get("review_priority", "normal")

    # Escalate priority if high-confidence anomalies found
    if anomaly and anomaly.overall_risk == "high":
        review_priority = "urgent"

    review_request = ManualReviewRequest(
        submission_id=result.submission_id,
        student_id=request.student_id,
        assignment_id=request.assignment_id,
        automated_score=result.automated_score,
        anomaly_flags=anomaly.flags if anomaly else [],
        priority=review_priority,
        instructor_notes=reasoning.get("instructor_notes", ""),
    )
    result.manual_review = review_request

    # Persist to interfaces
    queue_for_review(review_request)

    if anomaly and anomaly.flags:
        report_anomaly(
            submission_id=result.submission_id,
            student_id=request.student_id,
            assignment_id=request.assignment_id,
            anomaly_report=anomaly,
        )

    return result
