"""
Internal types used across the ADFEL harness.

These are deliberately small Pydantic / dataclass types used inside the
agents and orchestrator. They're re-exported from `agentic_system` only for the
embedder's convenience (e.g., to read `TurnResult.guidance_level`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field as dc_field
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ----------------------------------------------------------------- enums
class ViolationType(str, Enum):
    DIRECT_SOLUTION_REQUEST = "DIRECT_SOLUTION_REQUEST"
    ANSWER_FARMING = "ANSWER_FARMING"


class ViolationSeverity(str, Enum):
    MAJOR = "MAJOR"
    MINOR = "MINOR"


class QuestionClassification(str, Enum):
    CONCEPTUAL = "CONCEPTUAL"
    PROCEDURAL = "PROCEDURAL"
    CLARIFICATION = "CLARIFICATION"
    DIRECT_SOLUTION = "DIRECT_SOLUTION"
    ANSWER_FARMING = "ANSWER_FARMING"


class GuidanceLevel(str, Enum):
    """Constraint shape Lab Companion adopts in its system prompt."""

    FULL = "FULL"
    MODERATE = "MODERATE"
    MINIMAL = "MINIMAL"
    REJECTED = "REJECTED"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"


# ----------------------------------------------------------------- records
class QuestionRecord(BaseModel):
    question_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sequence_number: int
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )
    text: str
    classification: QuestionClassification
    violation: bool
    violation_type: Optional[ViolationType] = None
    concept_tags: list[str] = Field(default_factory=list)


class ViolationRecord(BaseModel):
    violation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question_id: str
    sequence_number: int
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )
    violation_type: ViolationType
    severity: ViolationSeverity
    question_text: str


class VerificationRecord(BaseModel):
    verification_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question_id: Optional[str] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z"
    )
    passes: bool
    reason: Optional[str] = None
    guidance_level: GuidanceLevel = GuidanceLevel.FULL
    draft_excerpt: str = ""


# ----------------------------------------------------------------- agent results
@dataclass
class ValidateResult:
    classification: QuestionClassification
    guidance_level: GuidanceLevel
    violation_detected: bool
    violation_type: Optional[ViolationType]
    violation_count: int
    question_count: int
    session_escalated: bool


@dataclass
class VerifyResult:
    passes: bool
    reason: Optional[str]
    feedback_for_companion: Optional[str]


@dataclass
class StudentContext:
    total_questions: int
    summary: str
    avg_hint_level: float
    question_type_distribution: dict
    sessions_count: int
    raw: dict = dc_field(default_factory=dict)

    @classmethod
    def empty(cls) -> "StudentContext":
        return cls(
            total_questions=0,
            summary="New student - no previous interactions recorded.",
            avg_hint_level=0.0,
            question_type_distribution={},
            sessions_count=0,
            raw={},
        )


# ----------------------------------------------------------------- public results
@dataclass
class SessionState:
    """Opaque state object: the embedder holds it across turns and passes it back."""

    session_id: str
    student_context: StudentContext
    conversation_history: list[dict]
    student_id: Optional[str] = None


@dataclass
class TurnResult:
    """What `LabHarness.handle_turn` returns to the embedder per turn."""

    response: str
    guidance_level: str
    classification: str
    violation_detected: bool
    session_escalated: bool
    verifier_passes: bool
    retries: int
    fallback: bool
    # extra detail for richer UIs
    rag_docs_count: int = 0
    verify_reason: Optional[str] = None
    violation_count: int = 0
