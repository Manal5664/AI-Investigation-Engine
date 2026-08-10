from app.graph.base import GraphStore
from app.graph.models import GraphEdge
from app.graph.retriever import GraphRetriever
from app.schemas.graph import (
    GraphQueryRequest,
    GraphQueryResult,
    GraphQueryType,
)


class GraphRetrievalService:
    """Boundary for structural knowledge-graph queries."""

    def __init__(
        self,
        graph_store: GraphStore,
        retriever: GraphRetriever | None = None,
    ) -> None:
        self._store = graph_store
        self._retriever = retriever or GraphRetriever(graph_store)

    async def query(self, request: GraphQueryRequest) -> GraphQueryResult:
        query_type = request.query_type
        if query_type is GraphQueryType.ENTITIES_FOR_CLAIM:
            return await self._entities_for_claim(request)
        if query_type is GraphQueryType.EVIDENCE_FOR_SOURCE:
            return await self._evidence_for_source(request)
        if query_type is GraphQueryType.PATHS_BETWEEN:
            return await self._paths_between(request)
        if query_type is GraphQueryType.CONTRADICTING_EVIDENCE:
            return await self._contradicting_evidence(request)
        if query_type is GraphQueryType.SOURCES_MENTIONING:
            return await self._sources_mentioning(request)
        raise ValueError(f"Unsupported query type: {query_type}")

    async def _entities_for_claim(
        self,
        request: GraphQueryRequest,
    ) -> GraphQueryResult:
        nodes = await self._retriever.entities_related_to_claim(
            request.node_id,
            limit=request.limit,
        )
        return GraphQueryResult(
            query_type=request.query_type,
            query=request.node_id,
            nodes=nodes,
            edges=[],
            paths=[],
        )

    async def _evidence_for_source(
        self,
        request: GraphQueryRequest,
    ) -> GraphQueryResult:
        nodes = await self._retriever.strongest_evidence_for_source(
            request.node_id,
            limit=request.limit,
        )
        return GraphQueryResult(
            query_type=request.query_type,
            query=request.node_id,
            nodes=nodes,
            edges=[],
            paths=[],
        )

    async def _paths_between(
        self,
        request: GraphQueryRequest,
    ) -> GraphQueryResult:
        paths = await self._retriever.paths_between(
            request.node_id,
            request.target_node_id,
            max_depth=request.max_depth,
            limit=request.limit,
        )
        edges: list[GraphEdge] = []
        for path in paths:
            edges.extend(path.edges)
        return GraphQueryResult(
            query_type=request.query_type,
            query=f"{request.node_id} -> {request.target_node_id}",
            nodes=[],
            edges=edges,
            paths=paths,
        )

    async def _contradicting_evidence(
        self,
        request: GraphQueryRequest,
    ) -> GraphQueryResult:
        nodes = await self._retriever.contradicting_evidence_for_claim(
            request.node_id,
            limit=request.limit,
        )
        return GraphQueryResult(
            query_type=request.query_type,
            query=request.node_id,
            nodes=nodes,
            edges=[],
            paths=[],
        )

    async def _sources_mentioning(
        self,
        request: GraphQueryRequest,
    ) -> GraphQueryResult:
        nodes = await self._retriever.sources_mentioning(
            node_id=request.node_id,
            label=request.node_label,
            limit=request.limit,
        )
        return GraphQueryResult(
            query_type=request.query_type,
            query=request.node_label or request.node_id,
            nodes=nodes,
            edges=[],
            paths=[],
        )
