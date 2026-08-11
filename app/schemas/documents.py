"""API schemas for the document management subsystem."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.documents.models import (
    DocumentIngestionResult,
    DocumentKind,
    DocumentProvenance,
    DocumentStoreStats,
    ExtractedDocument,
    UploadedDocument,
)
from app.graph.models import GraphEdge, GraphNode
from app.schemas.investigation import (
    InvestigationCategory,
    InvestigationDepth,
    StrictModel,
)

NonEmptyText = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1),
]


class UploadDocumentsRequest(StrictModel):
    document_ids: list[NonEmptyText] = Field(min_length=1, max_length=20)


class UploadDocumentsResponse(StrictModel):
    status: Literal["completed"]
    documents: list[DocumentIngestionResult]


class ListDocumentsRequest(StrictModel):
    kind: DocumentKind | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class StoredDocumentSummary(StrictModel):
    uploaded: UploadedDocument
    page_count: int = Field(ge=0)
    character_count: int = Field(ge=0)
    extraction_method: NonEmptyText
    requires_vision_pages: int = Field(ge=0)


class ListDocumentsResponse(StrictModel):
    status: Literal["completed"]
    documents: list[StoredDocumentSummary]
    total: int = Field(ge=0)


class GetDocumentResponse(StrictModel):
    status: Literal["completed"]
    document: ExtractedDocument


class DeleteDocumentsRequest(StrictModel):
    document_ids: list[NonEmptyText] = Field(min_length=1, max_length=50)


class DeleteDocumentsResponse(StrictModel):
    status: Literal["completed"]
    deleted_count: int = Field(ge=0)


class DocumentStoreStatsResponse(StrictModel):
    status: Literal["completed"]
    stats: DocumentStoreStats


class DocumentGraphMappingRequest(StrictModel):
    document_id: str = Field(pattern=r"^doc-[0-9a-f]{12,64}$")


class DocumentGraphMappingResponse(StrictModel):
    status: Literal["completed"]
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class DocumentIndexResponse(StrictModel):
    status: Literal["completed", "skipped"]
    document_id: str = Field(pattern=r"^doc-[0-9a-f]{12,64}$")
    pages_indexed: int = Field(ge=0)
    chunks_created: int = Field(ge=0)
    duplicates_skipped: int = Field(ge=0)
    failures: list[str] = Field(default_factory=list)


class DocumentExcerpt(StrictModel):
    document_id: str = Field(pattern=r"^doc-[0-9a-f]{12,64}$")
    filename: NonEmptyText
    page_number: int = Field(ge=1)
    text: NonEmptyText


class DocumentUsedRef(StrictModel):
    document_id: str = Field(pattern=r"^doc-[0-9a-f]{12,64}$")
    filename: NonEmptyText
    page_count: int = Field(ge=0)
    pages_used: list[int] = Field(default_factory=list)


class DocumentInvestigationRequest(StrictModel):
    query: NonEmptyText
    depth: InvestigationDepth = InvestigationDepth.STANDARD
    document_ids: list[NonEmptyText] | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    use_rag: bool = True
    use_graph: bool = True


class DocumentInvestigationReport(StrictModel):
    status: Literal["completed", "no_documents"]
    query: NonEmptyText
    depth: InvestigationDepth
    category: InvestigationCategory
    findings: list[str] = Field(min_length=1)
    supporting_excerpts: list[DocumentExcerpt] = Field(default_factory=list)
    contradicted_claims: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    documents_used: list[DocumentUsedRef] = Field(default_factory=list)
    provider_used: NonEmptyText
    model_used: NonEmptyText
    fallback_used: bool


__all__ = [
    "DeleteDocumentsRequest",
    "DeleteDocumentsResponse",
    "DocumentExcerpt",
    "DocumentGraphMappingRequest",
    "DocumentGraphMappingResponse",
    "DocumentIndexResponse",
    "DocumentInvestigationReport",
    "DocumentInvestigationRequest",
    "DocumentProvenance",
    "DocumentStoreStatsResponse",
    "DocumentUsedRef",
    "GetDocumentResponse",
    "ListDocumentsRequest",
    "ListDocumentsResponse",
    "StoredDocumentSummary",
    "UploadDocumentsRequest",
    "UploadDocumentsResponse",
]
