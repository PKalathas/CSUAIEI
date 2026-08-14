"""
Report Generator — builds and persists integrity reports.

Two public functions:
  generate_session_report()   — end-of-session summary for Instructor Co-pilot
  generate_post_lab_report()  — cross-session over-reliance analysis
"""

import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from models import FinalStatus, QuestionClassification, ReportType

if TYPE_CHECKING:
    from cosmos_client import CosmosIntegrityClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session report
# ---------------------------------------------------------------------------

async def generate_session_report(
    session_doc: dict,
    cosmos: "CosmosIntegrityClient",
) -> dict:
    """
    Build and persist a SESSION integrity report in the Cosmos DB 'reports' container.

    Returns the stored report document.
    """
    violations = session_doc.get("violations", [])
    questions = session_doc.get("questions", [])
    total_questions = session_doc.get("question_count", len(questions))
    violation_count = session_doc.get("violation_count", len(violations))
    escalated = session_doc.get("escalated", False)

    # classification distribution
    classification_distribution = {c.value: 0 for c in QuestionClassification}
    for q in questions:
        cls = q.get("classification")
        if cls in classification_distribution:
            classification_distribution[cls] += 1

    # concept struggle summary — concepts from violation questions
    concept_violation_counts: dict[str, list[str]] = {}
    for q in questions:
        if q.get("violation"):
            for tag in q.get("concept_tags", []):
                if tag not in concept_violation_counts:
                    concept_violation_counts[tag] = []
                concept_violation_counts[tag].append(
                    q.get("violation_type", "UNKNOWN")
                )
    concept_struggle_summary = [
        {
            "concept": concept,
            "count": len(vtypes),
            "violation_types": list(set(vtypes)),
        }
        for concept, vtypes in concept_violation_counts.items()
    ]

    # final status
    if escalated:
        final_status = FinalStatus.ESCALATED.value
    elif violation_count > 0:
        final_status = FinalStatus.WARNING.value
    else:
        final_status = FinalStatus.CLEAN.value

    # escalation log
    escalation_ts = None
    escalation_reason = None
    if escalated and violations:
        third = violations[2] if len(violations) >= 3 else violations[-1]
        escalation_ts = third.get("timestamp")
        escalation_reason = (
            f"Violation threshold (3) exceeded. "
            f"Final violation type: {third.get('violation_type', 'unknown')}"
        )

    report_id = str(uuid.uuid4())
    report = {
        "id": report_id,
        "report_id": report_id,
        "student_id": session_doc["student_id"],
        "session_id": session_doc["session_id"],
        "lab_id": session_doc.get("lab_id", ""),
        "course_id": session_doc.get("course_id", "CSC580"),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "report_type": ReportType.SESSION.value,
        "summary": {
            "total_questions": total_questions,
            "violation_count": violation_count,
            "escalated": escalated,
            "final_status": final_status,
            "classification_distribution": classification_distribution,
            "concept_struggle_summary": concept_struggle_summary,
        },
        "violations_detail": violations,
        "escalation_log": {
            "escalated": escalated,
            "escalation_timestamp": escalation_ts,
            "reason": escalation_reason,
        },
        "instructor_notes": "",
        "raw_session_snapshot": session_doc,
    }

    await cosmos.create_report(report)
    logger.info(
        "Session report %s generated for student=%s session=%s status=%s",
        report_id,
        session_doc["student_id"],
        session_doc["session_id"],
        final_status,
    )
    return report


# ---------------------------------------------------------------------------
# Post-lab over-reliance report
# ---------------------------------------------------------------------------

async def generate_post_lab_report(
    student_id: str,
    session_docs: list[dict],
    lab_id: str,
    cosmos: "CosmosIntegrityClient",
) -> dict:
    """
    Analyse multiple sessions for a single lab assignment and produce a
    POST_LAB over-reliance report.

    Returns the stored report document.
    """
    if not session_docs:
        raise ValueError("session_docs must not be empty.")

    all_questions: list[dict] = []
    all_violations: list[dict] = []
    any_escalated = False

    for s in session_docs:
        all_questions.extend(s.get("questions", []))
        all_violations.extend(s.get("violations", []))
        if s.get("escalated", False):
            any_escalated = True

    total_q = len(all_questions)

    # Indicator: high direct-solution attempt ratio
    total_direct_solution = sum(
        1 for q in all_questions
        if q.get("classification") == QuestionClassification.DIRECT_SOLUTION.value
    )
    high_direct_solution_ratio = (
        (total_direct_solution / total_q) > 0.2 if total_q > 0 else False
    )

    # Indicator: rapid successive questions (< 30 s apart)
    rapid_successive = _check_rapid_successive(all_questions)

    # Indicator: same violation type repeated 3+ times
    violation_type_counts: dict[str, int] = {}
    for v in all_violations:
        vt = v.get("violation_type", "UNKNOWN")
        violation_type_counts[vt] = violation_type_counts.get(vt, 0) + 1
    repeated_violation_types = {
        vt: count for vt, count in violation_type_counts.items() if count >= 3
    }

    # Indicator: concept struggle areas — concepts that appeared in violation questions
    violation_concept_counts: dict[str, int] = {}
    for q in all_questions:
        if q.get("violation"):
            for tag in q.get("concept_tags", []):
                violation_concept_counts[tag] = violation_concept_counts.get(tag, 0) + 1
    concept_struggle_areas = [
        {"concept": c, "count": n}
        for c, n in sorted(violation_concept_counts.items(), key=lambda x: -x[1])
    ]

    indicators = {
        "high_direct_solution_ratio": high_direct_solution_ratio,
        "rapid_successive_questions": rapid_successive,
        "escalated_any_session": any_escalated,
        "repeated_violation_types": repeated_violation_types,
        "concept_struggle_areas": concept_struggle_areas,
    }

    flagged_count = sum([
        1 if high_direct_solution_ratio else 0,
        1 if rapid_successive else 0,
        1 if any_escalated else 0,
        1 if repeated_violation_types else 0,
        1 if concept_struggle_areas else 0,
    ])

    if flagged_count == 0:
        summary = "No over-reliance indicators detected."
    elif flagged_count == 1:
        summary = "1 over-reliance indicator detected. Recommend instructor review."
    else:
        summary = (
            f"{flagged_count} over-reliance indicators detected. "
            "Strong recommendation for instructor review."
        )

    report_id = str(uuid.uuid4())
    report = {
        "id": report_id,
        "report_id": report_id,
        "student_id": student_id,
        "lab_id": lab_id,
        "session_ids": [s["session_id"] for s in session_docs],
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "report_type": ReportType.POST_LAB.value,
        "summary_text": summary,
        "stats": {
            "total_questions": total_q,
            "total_violations": len(all_violations),
            "sessions_analysed": len(session_docs),
        },
        "over_reliance_indicators": indicators,
        "violations_detail": all_violations,
        "instructor_notes": "",
    }

    await cosmos.create_report(report)
    logger.info(
        "Post-lab report %s generated for student=%s lab=%s flags=%d",
        report_id,
        student_id,
        lab_id,
        flagged_count,
    )
    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_rapid_successive(questions: list[dict]) -> bool:
    """Return True if any two consecutive questions were asked < 30 seconds apart."""
    from datetime import timezone

    timestamps = []
    for q in questions:
        ts_str = q.get("timestamp")
        if ts_str:
            try:
                ts_str_clean = ts_str.replace("Z", "+00:00")
                ts = datetime.fromisoformat(ts_str_clean)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                timestamps.append(ts)
            except ValueError:
                pass

    for i in range(1, len(timestamps)):
        delta = (timestamps[i] - timestamps[i - 1]).total_seconds()
        if 0 < delta < 30:
            return True
    return False
