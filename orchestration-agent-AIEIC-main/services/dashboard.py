"""
Dashboard aggregation service.

Combines data from Curriculum Designer, Participant Agent, and Assessment Agent
into a single DashboardResponse payload for the instructor frontend.

Why NOT LangGraph here:
  LangGraph shines for sequential/conditional flows. The dashboard is purely
  parallel — we fire three independent HTTP calls and join them. asyncio.gather
  is the right tool: simpler, faster, easier to debug.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aieic_shared.clients.assessment import AssessmentClient
from aieic_shared.clients.curriculum import CurriculumClient
from aieic_shared.clients.participant import ParticipantClient
from aieic_shared.schemas.core import LabPhase, StudentStatus
from aieic_shared.schemas.orchestrator import (
    AIAssistanceStats,
    DashboardActivityBlock,
    DashboardActivityCard,
    DashboardGradesBlock,
    DashboardGradesRow,
    DashboardLabInfo,
    DashboardMaterialBlock,
    DashboardResponse,
    DashboardStatsBlock,
    GradeDistribution,
    PerStudentRow,
)

logger = logging.getLogger(__name__)

# ── v0.1 hardcoded roster ─────────────────────────────────────────────────────
# Replace with a real /roster endpoint when the LMS integration is ready.
ENROLLED_STUDENTS: list[str] = [
    "alex_m", "bella_k", "carlos_r", "dana_w", "ethan_l",
    "fiona_s", "jake_n", "nina_q", "george_t",
]

DISPLAY_NAMES: dict[str, str] = {
    "alex_m": "Alex M",
    "bella_k": "Bella K",
    "carlos_r": "Carlos R",
    "dana_w": "Dana W",
    "ethan_l": "Ethan L",
    "fiona_s": "Fiona S",
    "jake_n": "Jake N",
    "nina_q": "Nina Q",
    "george_t": "George T",
}


class DashboardService:
    """
    Fetches and assembles the instructor dashboard payload.

    Inject real or mock clients — the service doesn't care.
    """

    def __init__(
        self,
        participant: ParticipantClient,
        assessment: AssessmentClient,
        curriculum: CurriculumClient,
    ) -> None:
        self.participant = participant
        self.assessment = assessment
        self.curriculum = curriculum

    async def build(
        self,
        lab_id: str,
        tab: Optional[str] = None,
    ) -> DashboardResponse:
        """
        Build the full dashboard response.

        If `tab` is specified (material | activity | grades | stats), only that
        block is populated — the others are None. This lets the frontend
        refresh individual tabs cheaply.
        """
        lab_info = DashboardLabInfo(
            lab_id=lab_id,
            title=f"Lab {lab_id.replace('lab', '').upper()}",
            phase=LabPhase.DURING_LAB,
            students_enrolled=len(ENROLLED_STUDENTS),
        )

        # Decide which blocks to fetch
        want_material = tab in (None, "material")
        want_activity = tab in (None, "activity")
        want_grades   = tab in (None, "grades", "stats")

        tasks, keys = [], []
        if want_material:
            tasks.append(self._fetch_material(lab_id)); keys.append("material")
        if want_activity:
            tasks.append(self._fetch_activity());       keys.append("activity")
        if want_grades:
            tasks.append(self._fetch_grades(lab_id));   keys.append("grades")

        results = await asyncio.gather(*tasks, return_exceptions=True)

        data: dict = {}
        for key, result in zip(keys, results):
            if isinstance(result, Exception):
                logger.warning(f"[dashboard] {key} fetch failed: {result}")
                data[key] = None
            else:
                data[key] = result

        stats = None
        if tab in (None, "stats") and data.get("grades"):
            stats = self._compute_stats(data["grades"], data.get("activity"))

        return DashboardResponse(
            lab=lab_info,
            material=data.get("material"),
            activity=data.get("activity"),
            grades=data.get("grades"),
            stats=stats,
        )

    # ── private helpers ───────────────────────────────────────────────────────

    async def _fetch_material(self, lab_id: str) -> DashboardMaterialBlock:
        try:
            material = await self.curriculum.get(lab_id)
            return DashboardMaterialBlock(curriculum=material)
        except Exception as e:
            logger.warning(f"[dashboard] Curriculum Designer unavailable: {e}")
            return DashboardMaterialBlock()

    async def _fetch_activity(self) -> DashboardActivityBlock:
        """
        Fetch each enrolled student's context in parallel, then classify
        into needs_help / flagged / on_track.

        v0.2 TODO: replace N individual calls with a single
        GET /participant/cohort/{lab_id} batch endpoint.
        """
        async def fetch_one(sid: str):
            try:
                ctx = await self.participant.get_student_context(sid)
                return sid, ctx
            except Exception as e:
                logger.warning(f"[dashboard] Could not fetch context for {sid}: {e}")
                return sid, None

        pairs = await asyncio.gather(*[fetch_one(sid) for sid in ENROLLED_STUDENTS])

        block = DashboardActivityBlock()
        for sid, ctx in pairs:
            if ctx is None:
                continue

            display = DISPLAY_NAMES.get(sid, sid)

            # Simple heuristic until Participant Agent exposes /status endpoint (v0.2)
            if ctx.avg_hint_level >= 3 or ctx.total_questions > 25:
                status = StudentStatus.NEEDS_HELP
            elif ctx.avg_hint_level >= 2.5:
                status = StudentStatus.FLAGGED
            else:
                status = StudentStatus.ON_TRACK

            top_topic: Optional[str] = None
            if ctx.question_type_distribution:
                top_topic = max(
                    ctx.question_type_distribution,
                    key=ctx.question_type_distribution.get,
                )

            card = DashboardActivityCard(
                student_id=sid,
                display_name=display,
                status=status,
                prompt_count=ctx.total_questions,
                top_topic=top_topic,
            )
            if status == StudentStatus.NEEDS_HELP:
                block.needs_help.append(card)
            elif status == StudentStatus.FLAGGED:
                block.flagged.append(card)
            else:
                block.on_track.append(card)

        return block

    async def _fetch_grades(self, lab_id: str) -> DashboardGradesBlock:
        try:
            results_raw, queue_raw = await asyncio.gather(
                self.assessment.list_results(assignment_id=lab_id),
                self.assessment.get_review_queue(),
                return_exceptions=True,
            )
        except Exception as e:
            logger.warning(f"[dashboard] Assessment Agent unavailable: {e}")
            return DashboardGradesBlock()

        results  = results_raw  if isinstance(results_raw, list)  else []
        queue    = queue_raw    if isinstance(queue_raw, list)    else []
        flagged_ids = {item.submission_id for item in queue}

        rows: list[DashboardGradesRow] = []
        for r in results:
            score = r.final_score if r.final_score is not None else r.automated_score

            is_high_risk = (
                r.anomaly_report
                and getattr(r.anomaly_report, "overall_risk", None) == "high"
            )
            if r.submission_id in flagged_ids or is_high_risk:
                row_status = "flagged"
            elif r.status == "completed":
                row_status = "graded"
            else:
                row_status = "needs_review"

            rows.append(DashboardGradesRow(
                submission_id=r.submission_id,
                student_id=r.student_id,
                display_name=DISPLAY_NAMES.get(r.student_id, r.student_id),
                score=score,
                status=row_status,
                ai_feedback_summary=r.feedback.summary if r.feedback else "",
            ))

        return DashboardGradesBlock(
            submissions_total=len(rows),
            auto_graded=sum(1 for row in rows if row.status == "graded"),
            needs_review=sum(1 for row in rows if row.status == "needs_review"),
            flagged=sum(1 for row in rows if row.status == "flagged"),
            rows=rows,
        )

    def _compute_stats(
        self,
        grades: DashboardGradesBlock,
        activity: Optional[DashboardActivityBlock],
    ) -> DashboardStatsBlock:
        scores = [r.score for r in grades.rows if r.score is not None]
        avg = round(sum(scores) / len(scores), 1) if scores else 0.0

        dist = GradeDistribution()
        for s in scores:
            if s >= 90:   dist.a_90_100 += 1
            elif s >= 80: dist.b_80_89  += 1
            elif s >= 70: dist.c_70_79  += 1
            elif s >= 60: dist.d_60_69  += 1
            else:         dist.f_below_60 += 1

        all_cards: list[DashboardActivityCard] = []
        if activity:
            all_cards = (
                activity.needs_help
                + activity.flagged
                + activity.on_track
                + activity.inactive
            )

        grade_map = {r.student_id: r for r in grades.rows}
        per_student: list[PerStudentRow] = []
        for card in all_cards:
            grade_row = grade_map.get(card.student_id)
            per_student.append(PerStudentRow(
                student_id=card.student_id,
                display_name=card.display_name,
                score=grade_row.score if grade_row else None,
                prompts=card.prompt_count,
                hints=0,  # TODO: expose avg_hint_level count from Participant Agent
                status=card.status,
            ))

        return DashboardStatsBlock(
            class_average=avg,
            submissions=grades.submissions_total,
            auto_graded=grades.auto_graded,
            needs_review=grades.needs_review,
            flagged=grades.flagged,
            grade_distribution=dist,
            ai_assistance=AIAssistanceStats(),  # TODO: aggregate from Participant Agent
            per_student=per_student,
        )
