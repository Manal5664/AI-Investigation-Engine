"""Persist extracted document structure into the shared knowledge graph."""

from app.documents.base import DocumentStore
from app.documents.mappers import (
    build_document_graph_edges,
    build_document_graph_nodes,
)
from app.graph.base import GraphStore
from app.graph.models import GraphEdge, GraphNode


class DocumentGraphService:
    """Map stored documents into graph nodes and register them in the store."""

    def __init__(
        self,
        graph_store: GraphStore,
        document_store: DocumentStore,
    ) -> None:
        self._graph_store = graph_store
        self._document_store = document_store

    async def index_document(
        self,
        document_id: str,
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        """Add every node and edge derived from a stored document."""
        stored = await self._document_store.get(document_id)
        if stored is None:
            return [], []

        nodes = build_document_graph_nodes(stored.extracted)
        edges = build_document_graph_edges(stored.extracted)
        for node in nodes:
            await self._graph_store.add_node(node)
        for edge in edges:
            await self._graph_store.add_edge(edge)
        return nodes, edges


__all__ = ["DocumentGraphService"]
