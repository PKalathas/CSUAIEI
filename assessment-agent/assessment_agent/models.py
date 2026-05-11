from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime
import uuid


class SubmissionType(str, Enum):
    CODE_ONLY = "code_only"
    REPORT_ONLY = "report_only"
    FULL = "full"


class TestCase(BaseModel):
    name: str
    input: str
    expected_output: str
    points: float = 10.0
    timeout_seconds: float = 5.0
    description: str = ""


class TestCaseResult(BaseModel):
    name: str
    passed: bool
    expected_output: str
    actual_output: str = ""
    error: str = ""
    execution_time_ms: float = 0.0
    points_earned: float = 0.0
    points_possible: float = 10.0


class CodeGradeResult(BaseModel):
    test_results: list[TestCaseResult] = []
    tests_passed: int = 0
    tests_total: int = 0
    raw_score: float = 0.0  # 0-100
    weighted_score: float = 0.0  # raw_score * 0.60
    compilation_error: str = ""
    runtime_errors: list[str] = []


class ReportCriterion(BaseModel):
    name: str
    score: float = 0.0  # 0-10
    max_score: float = 10.0
    justification: str = ""


class ReportEvaluation(BaseModel):
    criteria: list[ReportCriterion] = []
    raw_score: float = 0.0  # 0-100
    weighted_score: float = 0.0  # raw_score * 0.30
    llm_reasoning: str = ""


class AnomalyFlag(BaseModel):
    flag_type: str  # "style_change", "plagiarism", "ai_generated", "complexity_mismatch"
    confidence: float = 0.0  # 0.0 - 1.0
    evidence: str = ""
    severity: str = "low"  # low, medium, high


class AnomalyReport(BaseModel):
    flags: list[AnomalyFlag] = []
    overall_risk: str = "low"  # low, medium, high
    recommendation: str = ""


class FeedbackReport(BaseModel):
    summary: str = ""
    strengths: list[str] = []
    improvements: list[str] = []
    next_steps: list[str] = []
    detailed_feedback: str = ""  # Full markdown feedback


class LLMCallRecord(BaseModel):
    stage: str
    model_id: str
    prompt_hash: str
    prompt_text: str
    raw_response: str
    latency_ms: int
    success: bool = True
    error: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ProvenanceRecord(BaseModel):
    code_hash: Optional[str] = None
    report_hash: Optional[str] = None
    rubric_hash: str = ""
    model_id: str = ""
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)
    total_latency_ms: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ProvenanceCollector:
    """Runtime accumulator passed through the pipeline to collect LLM call records."""

    def __init__(
        self,
        model_id: str,
        rubric_hash: str,
        code_hash: Optional[str] = None,
        report_hash: Optional[str] = None,
    ) -> None:
        self.model_id = model_id
        self.rubric_hash = rubric_hash
        self.code_hash = code_hash
        self.report_hash = report_hash
        self._calls: list[LLMCallRecord] = []

    def add_call(self, record: LLMCallRecord) -> None:
        self._calls.append(record)

    def build(self) -> ProvenanceRecord:
        return ProvenanceRecord(
            code_hash=self.code_hash,
            report_hash=self.report_hash,
            rubric_hash=self.rubric_hash,
            model_id=self.model_id,
            prompt_versions={c.stage: c.prompt_hash for c in self._calls if c.success},
            llm_calls=self._calls,
            total_latency_ms=sum(c.latency_ms for c in self._calls),
        )


class ManualReviewRequest(BaseModel):
    submission_id: str
    student_id: str
    assignment_id: str
    automated_score: float
    anomaly_flags: list[AnomalyFlag] = []
    priority: str = "normal"  # low, normal, high, urgent
    status: str = "pending"  # pending, in_review, completed
    instructor_score: Optional[float] = None
    instructor_notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class AssessmentResult(BaseModel):
    submission_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    student_id: str
    assignment_id: str
    submission_type: SubmissionType
    code_grade: Optional[CodeGradeResult] = None
    report_evaluation: Optional[ReportEvaluation] = None
    anomaly_report: Optional[AnomalyReport] = None
    feedback: Optional[FeedbackReport] = None
    manual_review: Optional[ManualReviewRequest] = None
    automated_score: float = 0.0  # Combined weighted score (code 60% + report 30%)
    final_score: Optional[float] = None  # After instructor review adds 10%
    status: str = "completed"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    agent_reasoning: str = ""  # The orchestrator's chain-of-thought
    provenance: Optional[ProvenanceRecord] = None


class AssessmentRequest(BaseModel):
    student_id: str
    assignment_id: str
    code: Optional[str] = None
    report: Optional[str] = None
    submission_type: Optional[SubmissionType] = None
