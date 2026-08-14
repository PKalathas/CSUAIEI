"""Pydantic models for the server HTTP API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateSessionResponse(BaseModel):
    session_id: str
    total_questions: int
    resuming: bool


class TurnRequest(BaseModel):
    message: str


# --------------------------------------------------------------- auth (CAS)
class CasValidateRequest(BaseModel):
    # Only the CAS service ticket — the server uses its own configured
    # ``service`` URL for validation so the two legs can't drift.
    ticket: str


class CasValidateResponse(BaseModel):
    token: str
    expires_in: int


class StepEvent(BaseModel):
    name: str
    type: str
    output: str


class FileResult(BaseModel):
    filename: str
    blob_url: str
    error: str | None = None


class UploadResponse(BaseModel):
    files: list[FileResult]
    indexer_triggered: bool
    message: str


class IndexerStatusResponse(BaseModel):
    status: str
    last_result: dict | None = None


class TurnResultResponse(BaseModel):
    response: str
    guidance_level: str
    classification: str
    violation_detected: bool
    session_escalated: bool
    verifier_passes: bool
    retries: int
    fallback: bool
    rag_docs_count: int = 0
    verify_reason: str | None = None
    violation_count: int = 0


# ----------------------------------------------------------- admin / multi-tenant
UserRole = Literal["admin", "instructor", "student"]


class UserCreate(BaseModel):
    email: str
    name: str = ""
    role: UserRole = "student"


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: UserRole
    sso_subject: Optional[str] = None
    created_at: str


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # Optional overrides — if omitted, the server derives the conventional
    # ``course-{uuid_short}-{idx,indexer,ds}`` names. Useful when an admin
    # has pre-provisioned a specific index in Azure.
    blob_container_name: Optional[str] = None
    search_index_name: Optional[str] = None
    search_indexer_name: Optional[str] = None
    search_datasource_name: Optional[str] = None


class CoursePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)


class CourseOut(BaseModel):
    id: str
    name: str
    instructor_id: str
    blob_container_name: str
    search_index_name: str
    search_indexer_name: str
    search_datasource_name: str
    created_at: str


class CourseDeleteResponse(BaseModel):
    id: str
    leftover_resources: dict


class EnrollRequest(BaseModel):
    email: str
    name: str = ""


class EnrollmentOut(BaseModel):
    course_id: str
    user: UserOut
    enrolled_at: str
