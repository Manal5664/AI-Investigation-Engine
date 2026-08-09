from datetime import datetime
from typing import Annotated

from pydantic import Field, HttpUrl, StringConstraints

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
    snippet: str = Field(min_length=1)
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
