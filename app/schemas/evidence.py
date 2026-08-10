from datetime import datetime
from enum import Enum

from pydantic import AliasChoices, Field, HttpUrl

from app.schemas.investigation import QueryText, StrictModel
from app.schemas.source import Source


class EvidenceStance(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"
    INSUFFICIENT = "insufficient"


class EvidenceStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    UNKNOWN = "unknown"


class EvidenceProvenance(StrictModel):
    source_id: str = Field(pattern=r"^source-\d{3}$")
    source_url: HttpUrl
    relevant_passage: str = Field(min_length=1)
    retrieval_timestamp: datetime = Field(
        validation_alias=AliasChoices(
            "retrieval_timestamp",
            "retrieved_at",
        )
    )
    extraction_method: str = Field(min_length=1)
    model_used: str = Field(min_length=1)
    content_hash: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    location: str | None = None

    @property
    def retrieved_at(self) -> datetime:
        """Backward-compatible attribute for the pre-Phase 5 field name."""
        return self.retrieval_timestamp


class EvidenceItem(StrictModel):
    evidence_id: str = Field(pattern=r"^evidence-\d{3}$")
    sub_question_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    stance: EvidenceStance
    strength: EvidenceStrength
    provenance: EvidenceProvenance


class EvidenceStanceCounts(StrictModel):
    supports: int = Field(default=0, ge=0)
    contradicts: int = Field(default=0, ge=0)
    neutral: int = Field(default=0, ge=0)
    insufficient: int = Field(default=0, ge=0)


class EvidenceSummary(StrictModel):
    supporting_items: int = Field(ge=0)
    contradicting_items: int = Field(ge=0)
    neutral_items: int = Field(ge=0)
    insufficient_items: int = Field(ge=0)
    strongest_supporting_evidence: EvidenceItem | None = None
    strongest_contradicting_evidence: EvidenceItem | None = None
    unresolved_conflicts: list[str]


class EvidenceExtractionCandidate(StrictModel):
    source_id: str = Field(pattern=r"^source-\d{3}$")
    source_url: HttpUrl
    relevant_passage: str = Field(min_length=1)
    stance: EvidenceStance
    strength: EvidenceStrength
    rationale: str = Field(min_length=1)


class EvidenceExtractionPayload(StrictModel):
    evidence_items: list[EvidenceExtractionCandidate]


class EvidenceExtractionRequest(StrictModel):
    query: QueryText
    sub_question: str = Field(min_length=5)
    sources: list[Source] = Field(min_length=1, max_length=10)


class EvidenceExtractionResponse(StrictModel):
    provider_used: str = Field(min_length=1)
    model_used: str = Field(min_length=1)
    evidence_items: list[EvidenceItem]
    stance_counts: EvidenceStanceCounts
    warnings: list[str]


class ConflictingSourceClaim(StrictModel):
    supporting_evidence_id: str = Field(pattern=r"^evidence-\d{3}$")
    supporting_source_id: str = Field(pattern=r"^source-\d{3}$")
    contradicting_evidence_id: str = Field(pattern=r"^evidence-\d{3}$")
    contradicting_source_id: str = Field(pattern=r"^source-\d{3}$")
    description: str = Field(min_length=1)


class EvidenceConflictReport(StrictModel):
    sub_question_id: str = Field(min_length=1)
    has_supporting_and_contradicting_evidence: bool
    conflicting_source_claims: list[ConflictingSourceClaim]
    unresolved_conflicts: list[str]


class ProviderFailure(StrictModel):
    error_type: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool
    retry_after_seconds: float | None = Field(default=None, ge=0)
