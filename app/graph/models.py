from enum import Enum
from typing import Literal

from pydantic import Field

from app.schemas.investigation import StrictModel


class GraphNodeType(str, Enum):
    INVESTIGATION = "investigation"
    CLAIM = "claim"
    SOURCE = "source"
    EVIDENCE = "evidence"
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    EVENT = "event"
    TOPIC = "topic"


class GraphRelationType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CITES = "cites"
    MENTIONS = "mentions"
    PUBLISHED_BY = "published_by"
    AUTHORED_BY = "authored_by"
    RELATED_TO = "related_to"
    OCCURRED_AT = "occurred_at"
    OCCURRED_ON = "occurred_on"
    INVESTIGATES = "investigates"
    DERIVED_FROM = "derived_from"
    CHALLENGES = "challenges"


class GraphProvenance(StrictModel):
    """References to the grounded material a node or edge came from."""

    source_id: str | None = Field(
        default=None,
        pattern=r"^source-\d{3}$",
    )
    evidence_id: str | None = Field(
        default=None,
        pattern=r"^evidence-\d{3}$",
    )
    url: str | None = None
    description: str | None = Field(default=None, min_length=1)


class GraphNode(StrictModel):
    node_id: str = Field(min_length=1, max_length=128)
    node_type: GraphNodeType
    label: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=4000)
    metadata: dict[str, str] = Field(default_factory=dict)
    provenance: list[GraphProvenance] = Field(default_factory=list)


class GraphEdge(StrictModel):
    edge_id: str = Field(min_length=1, max_length=128)
    source_node_id: str = Field(min_length=1, max_length=128)
    target_node_id: str = Field(min_length=1, max_length=128)
    relation_type: GraphRelationType
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: list[GraphProvenance] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class GraphNeighbor(StrictModel):
    node: GraphNode
    edge: GraphEdge
    direction: Literal["out", "in"]


class GraphPath(StrictModel):
    start_node_id: str = Field(min_length=1)
    end_node_id: str = Field(min_length=1)
    node_ids: list[str] = Field(min_length=2)
    edges: list[GraphEdge] = Field(min_length=1)


class GraphStats(StrictModel):
    store_type: str = Field(min_length=1)
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    investigation_count: int = Field(ge=0)
    counts_by_node_type: dict[str, int] = Field(default_factory=dict)
    counts_by_relation_type: dict[str, int] = Field(default_factory=dict)
