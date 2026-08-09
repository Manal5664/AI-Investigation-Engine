from datetime import datetime
from typing import Annotated

from pydantic import Field, HttpUrl, StringConstraints, model_validator

from app.schemas.evidence import EvidenceItem, EvidenceStanceCounts
from app.schemas.investigation import (
    InvestigationDepth,
    InvestigationSubQuestion,
    QueryText,
    StrictModel,
)
from app.schemas.source import Source, SourceMetadata, SourceType


SubQuestionText = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=5),
]


class SearchResult(StrictModel):
    title: str = Field(min_length=1)
    url: HttpUrl
    snippet: str | None = Field(default=None, min_length=1)
    source_type: SourceType
    published_at: datetime | None = None
    retrieved_at: datetime
    author: str | None = None
    publisher: str | None = None
    metadata: SourceMetadata = Field(default_factory=SourceMetadata)


class ResearchRequest(StrictModel):
    investigation_query: QueryText
    sub_question: SubQuestionText | None = None
    max_results: int = Field(default=5, ge=1, le=20)
    depth: InvestigationDepth = InvestigationDepth.STANDARD


class ResearchResult(StrictModel):
    investigation_query: QueryText
    depth: InvestigationDepth
    sub_question: InvestigationSubQuestion
    sources: list[Source]
    evidence_items: list[EvidenceItem]
    counts_by_stance: EvidenceStanceCounts
    warnings: list[str]


class GroundingCitation(StrictModel):
    source_id: str | None = Field(
        default=None,
        pattern=r"^source-\d{3}$",
    )
    source_title: str = Field(min_length=1)
    source_url: HttpUrl
    cited_text: str | None = Field(default=None, min_length=1)
    start_index: int | None = Field(default=None, ge=0)
    end_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> "GroundingCitation":
        if (self.start_index is None) != (self.end_index is None):
            raise ValueError(
                "start_index and end_index must both be provided or omitted"
            )
        if (
            self.start_index is not None
            and self.end_index is not None
            and self.end_index <= self.start_index
        ):
            raise ValueError("end_index must be greater than start_index")
        return self


class WebGroundingMetadata(StrictModel):
    search_queries: list[str] = Field(default_factory=list)
    citations: list[GroundingCitation] = Field(default_factory=list)
    search_suggestions_html: str | None = None


class GroundedSearchResponse(StrictModel):
    query: QueryText
    provider_used: str = Field(min_length=1)
    model_used: str = Field(min_length=1)
    results: list[SearchResult]
    grounded_summary: str | None = Field(default=None, min_length=1)
    grounding_metadata: WebGroundingMetadata
    warnings: list[str]


class WebResearchRequest(StrictModel):
    query: QueryText
    max_results: int = Field(default=5, ge=1, le=20)


class WebResearchResult(StrictModel):
    query: QueryText
    provider_used: str = Field(min_length=1)
    model_used: str = Field(min_length=1)
    sources: list[Source]
    grounded_summary: str | None = Field(default=None, min_length=1)
    grounding_metadata: WebGroundingMetadata
    warnings: list[str]
