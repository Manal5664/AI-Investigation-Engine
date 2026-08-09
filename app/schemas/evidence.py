from datetime import datetime
from enum import Enum

from pydantic import Field, HttpUrl

from app.schemas.investigation import StrictModel


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
    retrieved_at: datetime
    extraction_method: str = Field(min_length=1)
    content_hash: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    location: str | None = None


class EvidenceItem(StrictModel):
    evidence_id: str = Field(pattern=r"^evidence-\d{3}$")
    sub_question_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
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
