from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, StringConstraints, model_validator

from app.graph.models import (
    GraphEdge,
    GraphNode,
    GraphPath,
    GraphProvenance,
    GraphStats,
)
from app.schemas.evidence import (
    EvidenceConflictReport,
    EvidenceItem,
)
from app.schemas.investigation import (
    InvestigationDepth,
    InvestigationSubQuestion,
    QueryText,
    StrictModel,
)
from app.schemas.rag import RetrievalResult
from app.schemas.source import Source


NonEmptyText = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1),
]

InvestigationId = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]


class GraphBuildRequest(StrictModel):
    investigation_id: InvestigationId
    query: QueryText
    depth: InvestigationDepth = InvestigationDepth.STANDARD
    sub_questions: list[InvestigationSubQuestion] = Field(
        default_factory=list
    )
    sources: list[Source] = Field(default_factory=list)
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    conflicts: list[EvidenceConflictReport] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_claims(self) -> "GraphBuildRequest":
        claim_ids = {question.id for question in self.sub_questions}
        for item in self.evidence_items:
            if item.sub_question_id not in claim_ids:
                raise ValueError(
                    "Evidence must reference a supplied sub-question"
                )
        return self


class GraphBuildResult(StrictModel):
    investigation_id: InvestigationId
    nodes_added: int = Field(ge=0)
    edges_added: int = Field(ge=0)
    duplicates_skipped: int = Field(ge=0)
    claims_built: int = Field(ge=0)
    sources_built: int = Field(ge=0)
    evidence_built: int = Field(ge=0)
    entities_extracted: int = Field(ge=0)
    relations_extracted: int = Field(ge=0)
    warnings: list[str]
    stats: GraphStats


class GraphQueryType(str, Enum):
    ENTITIES_FOR_CLAIM = "entities_for_claim"
    EVIDENCE_FOR_SOURCE = "evidence_for_source"
    PATHS_BETWEEN = "paths_between"
    CONTRADICTING_EVIDENCE = "contradicting_evidence"
    SOURCES_MENTIONING = "sources_mentioning"


class GraphQueryRequest(StrictModel):
    query_type: GraphQueryType
    node_id: str | None = Field(default=None, min_length=1, max_length=128)
    target_node_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )
    node_label: str | None = Field(default=None, min_length=1)
    limit: int = Field(default=20, ge=1, le=100)
    max_depth: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def validate_fields(self) -> "GraphQueryRequest":
        if self.query_type in {
            GraphQueryType.ENTITIES_FOR_CLAIM,
            GraphQueryType.EVIDENCE_FOR_SOURCE,
            GraphQueryType.CONTRADICTING_EVIDENCE,
        }:
            if not self.node_id:
                raise ValueError(
                    f"{self.query_type.value} requires a node_id"
                )
        if self.query_type is GraphQueryType.PATHS_BETWEEN:
            if not self.node_id or not self.target_node_id:
                raise ValueError(
                    "paths_between requires node_id and target_node_id"
                )
        if self.query_type is GraphQueryType.SOURCES_MENTIONING:
            if not self.node_id and not self.node_label:
                raise ValueError(
                    "sources_mentioning requires node_id or node_label"
                )
        return self


class GraphQueryResult(StrictModel):
    query_type: GraphQueryType
    query: str | None = None
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    paths: list[GraphPath]


class GraphRAGContextItem(StrictModel):
    kind: Literal["vector", "source", "claim", "evidence", "entity"]
    text: str = Field(min_length=1)
    node_id: str | None = Field(default=None, max_length=128)
    node_type: str | None = None
    source_id: str | None = Field(
        default=None,
        pattern=r"^source-\d{3}$",
    )
    source_url: HttpUrl | None = None
    score: float = Field(ge=0.0, le=1.0)
    provenance: list[GraphProvenance] = Field(default_factory=list)


class GraphRAGRequest(StrictModel):
    query: QueryText
    investigation_id: InvestigationId
    top_k_vector: int = Field(default=5, ge=1, le=100)
    top_k_graph: int = Field(default=10, ge=1, le=100)
    max_path_depth: int = Field(default=5, ge=1, le=10)
    merged_context_limit: int = Field(default=20, ge=1, le=100)
    source_ids: list[NonEmptyText] | None = Field(default=None, min_length=1)
    source_urls: list[HttpUrl] | None = Field(default=None, min_length=1)


class GraphRAGResult(StrictModel):
    query: QueryText
    vector_matches: list[RetrievalResult]
    graph_matches: list[GraphNode]
    graph_paths: list[GraphPath]
    merged_context: list[GraphRAGContextItem]
    provenance: list[GraphProvenance]


__all__ = [
    "GraphBuildRequest",
    "GraphBuildResult",
    "GraphEdge",
    "GraphNode",
    "GraphPath",
    "GraphProvenance",
    "GraphQueryRequest",
    "GraphQueryResult",
    "GraphQueryType",
    "GraphRAGContextItem",
    "GraphRAGRequest",
    "GraphRAGResult",
    "GraphStats",
]
