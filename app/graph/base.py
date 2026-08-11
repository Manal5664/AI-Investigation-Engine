from abc import ABC, abstractmethod
from typing import Literal

from app.graph.models import (
    GraphEdge,
    GraphNeighbor,
    GraphNode,
    GraphPath,
    GraphStats,
)


class GraphStore(ABC):
    @property
    @abstractmethod
    def store_name(self) -> str:
        """Return the graph-store implementation identifier."""

    @abstractmethod
    async def add_node(self, node: GraphNode) -> bool:
        """Add a node; return False when a node with the same ID exists."""

    @abstractmethod
    async def add_edge(self, edge: GraphEdge) -> bool:
        """Add an edge; return False when it is a duplicate."""

    @abstractmethod
    async def get_node(self, node_id: str) -> GraphNode | None:
        """Return the node with the supplied ID, or None."""

    @abstractmethod
    async def get_neighbors(
        self,
        node_id: str,
        *,
        relation_type: str | None = None,
        direction: Literal["out", "in", "both"] = "both",
        limit: int = 100,
    ) -> list[GraphNeighbor]:
        """Return nodes connected to the supplied node."""

    @abstractmethod
    async def find_nodes(
        self,
        *,
        node_type: str | None = None,
        label: str | None = None,
        limit: int = 20,
    ) -> list[GraphNode]:
        """Return nodes matching an optional type and label text."""

    @abstractmethod
    async def find_paths(
        self,
        start_node_id: str,
        end_node_id: str,
        *,
        max_depth: int = 5,
        limit: int = 5,
    ) -> list[GraphPath]:
        """Return shortest paths between two nodes within a depth bound."""

    @abstractmethod
    async def delete_investigation(self, investigation_node_id: str) -> int:
        """Delete an investigation node and everything built for it."""

    @abstractmethod
    async def has_document(self, document_id: str) -> bool:
        """Return True when the store holds nodes derived from a document."""

    @abstractmethod
    async def clear(self) -> int:
        """Delete every stored node and edge; return the removed count."""

    @abstractmethod
    async def stats(self) -> GraphStats:
        """Return non-secret graph-store metadata."""
