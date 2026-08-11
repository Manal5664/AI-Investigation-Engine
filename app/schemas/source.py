from datetime import datetime
from enum import Enum

from pydantic import Field, HttpUrl

from app.schemas.investigation import StrictModel


class SourceType(str, Enum):
    ACADEMIC = "academic"
    GOVERNMENT = "government"
    OFFICIAL_ORGANIZATION = "official_organization"
    NEWS = "news"
    REFERENCE = "reference"
    BLOG = "blog"
    SOCIAL_MEDIA = "social_media"
    UNKNOWN = "unknown"


class CredibilityLevel(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    UNKNOWN = "unknown"


class SourceMetadata(StrictModel):
    language: str | None = None
    content_type: str | None = None
    citation_count: int | None = Field(default=None, ge=0)
    has_references: bool | None = None
    retrieval_provider: str | None = None
    retrieval_model: str | None = None
    retrieval_query: str | None = None
    grounding_citation_count: int | None = Field(default=None, ge=0)
    document_id: str | None = Field(
        default=None,
        pattern=r"^doc-[0-9a-f]{12,64}$",
    )
    document_filename: str | None = Field(default=None, min_length=1)
    document_page: int | None = Field(default=None, ge=1)


class SourceCredibility(StrictModel):
    level: CredibilityLevel
    score: int = Field(ge=0, le=100)
    reasons: list[str]
    warnings: list[str]
    disclaimer: str = (
        "This source-quality heuristic does not establish whether any claim "
        "or information is true."
    )


class Source(StrictModel):
    source_id: str = Field(pattern=r"^source-\d{3}$")
    title: str = Field(min_length=1)
    url: HttpUrl
    author: str | None = None
    publisher: str | None = None
    domain: str = Field(min_length=1)
    published_at: datetime | None = None
    retrieved_at: datetime
    source_type: SourceType
    snippet: str | None = None
    metadata: SourceMetadata = Field(default_factory=SourceMetadata)
    credibility: SourceCredibility | None = None
