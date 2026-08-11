"""Typed schemas for persisted entities and the Phase 10 API endpoints.

These double as repository DTOs: repositories accept and return these records
instead of leaking ORM models into services and routes.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import Field

from app.schemas.agentic import (
    AgentStepStatus,
    SynthesisConfidence,
)
from app.schemas.common import StrictResponseModel
from app.schemas.evidence import (
    EvidenceStance,
    EvidenceStrength,
)
from app.schemas.investigation import (
    InvestigationCategory,
    InvestigationDepth,
    StrictModel,
)
from app.schemas.source import SourceType

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class PersistenceStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Repository DTOs
# ---------------------------------------------------------------------------


class UserRecord(StrictModel):
    id: str = Field(pattern=r"^user-[0-9a-f]{12,64}$")
    email: str = Field(pattern=_EMAIL_PATTERN, max_length=320)
    display_name: str = Field(default="", min_length=0, max_length=200)
    created_at: datetime
    updated_at: datetime
    is_active: bool = True


class InvestigationStepRecord(StrictModel):
    step_id: str = Field(pattern=r"^step-\d{3}$")
    step_name: str = Field(min_length=1)
    status: AgentStepStatus
    step_order: int = Field(ge=1)
    started_at: datetime
    completed_at: datetime
    provider_used: str | None = None
    model_used: str | None = None
    action_summary: str = Field(min_length=1)
    input_references: list[str] = Field(default_factory=list)
    output_references: list[str] = Field(default_factory=list)
    source_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class SourceRecord(StrictModel):
    source_id: str = Field(pattern=r"^source-\d{3}$")
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    author: str | None = None
    publisher: str | None = None
    domain: str = Field(min_length=1)
    published_at: datetime | None = None
    retrieved_at: datetime
    source_type: SourceType
    snippet: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    credibility: dict[str, Any] | None = None


class EvidenceItemRecord(StrictModel):
    evidence_id: str = Field(pattern=r"^evidence-\d{3}$")
    sub_question_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    stance: EvidenceStance
    strength: EvidenceStrength
    source_id: str = Field(pattern=r"^source-\d{3}$")
    source_url: str = Field(min_length=1)
    source_title: str | None = None
    retrieval_timestamp: datetime
    relevant_passage: str = Field(min_length=1)
    extraction_method: str = Field(min_length=1)
    model_used: str = Field(min_length=1)
    content_hash: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    location: str | None = None


class ConflictRecord(StrictModel):
    sub_question_id: str = Field(min_length=1)
    has_supporting_and_contradicting_evidence: bool
    unresolved_conflicts: list[str] = Field(default_factory=list)
    conflicting_source_claims: list[dict[str, Any]] = Field(default_factory=list)


class InvestigationReportRecord(StrictModel):
    overall_evidence_picture: str = Field(min_length=1)
    confidence: SynthesisConfidence
    confidence_rationale: str = Field(default="", min_length=0)
    strongest_supporting_evidence: dict[str, Any] | None = None
    strongest_contradicting_evidence: dict[str, Any] | None = None
    unresolved_conflicts: list[str] = Field(default_factory=list)
    important_limitations: list[str] = Field(default_factory=list)
    alternative_explanations: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    created_at: datetime


class InvestigationRecord(StrictModel):
    id: str = Field(pattern=r"^inv-[0-9a-f]{12,64}$")
    user_id: str | None = Field(default=None, pattern=r"^user-[0-9a-f]{12,64}$")
    query: str = Field(min_length=5)
    depth: InvestigationDepth
    category: InvestigationCategory | None = None
    status: PersistenceStatus
    provider_used: str | None = None
    model_used: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    synthesis: str | None = None
    confidence: SynthesisConfidence | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    total_source_count: int = Field(ge=0)
    total_evidence_count: int = Field(ge=0)
    plan: dict[str, Any] | None = None


class InvestigationDetailRecord(StrictModel):
    investigation: InvestigationRecord
    steps: list[InvestigationStepRecord] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    evidence_items: list[EvidenceItemRecord] = Field(default_factory=list)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    report: InvestigationReportRecord | None = None


class DocumentRecord(StrictModel):
    document_id: str = Field(pattern=r"^doc-[0-9a-f]{12,64}$")
    filename: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    file_size_bytes: int = Field(ge=0)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: str = Field(min_length=1)
    extension: str = Field(min_length=1)
    extraction_method: str = Field(min_length=1)
    page_count: int = Field(ge=0)
    character_count: int = Field(ge=0)
    requires_vision_pages: int = Field(default=0, ge=0)
    received_at: datetime
    extracted_at: datetime
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API request/response schemas
# ---------------------------------------------------------------------------


class UserCreate(StrictModel):
    email: str = Field(pattern=_EMAIL_PATTERN, max_length=320)
    display_name: str = Field(default="", min_length=0, max_length=200)


class UserResponse(StrictResponseModel):
    status: Literal["completed"]
    user: UserRecord


class UserListResponse(StrictResponseModel):
    status: Literal["completed"]
    users: list[UserRecord]
    total: int = Field(ge=0)


class InvestigationSummaryResponse(StrictResponseModel):
    id: str = Field(pattern=r"^inv-[0-9a-f]{12,64}$")
    query: str = Field(min_length=5)
    depth: InvestigationDepth
    category: InvestigationCategory | None = None
    status: PersistenceStatus
    provider_used: str | None = None
    model_used: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    confidence: SynthesisConfidence | None = None
    total_source_count: int = Field(ge=0)
    total_evidence_count: int = Field(ge=0)


class InvestigationListResponse(StrictResponseModel):
    status: Literal["completed"]
    investigations: list[InvestigationSummaryResponse]
    total: int = Field(ge=0)


class InvestigationDetailResponse(StrictResponseModel):
    status: Literal["completed"]
    investigation: InvestigationRecord
    steps: list[InvestigationStepRecord]
    sources: list[SourceRecord]
    evidence_items: list[EvidenceItemRecord]
    conflicts: list[ConflictRecord]
    report: InvestigationReportRecord | None = None


class InvestigationDeleteResponse(StrictResponseModel):
    status: Literal["completed"]
    investigation_id: str
    deleted: bool


class DocumentListResponse(StrictResponseModel):
    status: Literal["completed"]
    documents: list[DocumentRecord]
    total: int = Field(ge=0)


class DocumentDeleteResponse(StrictResponseModel):
    status: Literal["completed"]
    document_id: str
    deleted: bool
