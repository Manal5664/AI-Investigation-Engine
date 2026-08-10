import re
from typing import ClassVar

from app.graph.base import GraphStore
from app.graph.models import (
    GraphNode,
    GraphProvenance,
)
from app.graph.retriever import GraphRetriever
from app.schemas.graph import (
    GraphRAGContextItem,
    GraphRAGRequest,
    GraphRAGResult,
)
from app.schemas.rag import RetrievalRequest
from app.services.rag_retrieval_service import RAGRetrievalService


class GraphRAGService:
    """Combine vector RAG retrieval with structural graph retrieval."""

    _ENTITY_TYPES: ClassVar[frozenset[str]] = frozenset(
        {"person", "organization", "location", "event", "topic"}
    )
    _STRENGTH_SCORES: ClassVar[dict[str, float]] = {
        "strong": 1.0,
        "moderate": 0.8,
        "weak": 0.6,
        "unknown": 0.5,
    }
    _MAX_PATHS = 5

    def __init__(
        self,
        *,
        rag_retrieval_service: RAGRetrievalService,
        graph_store: GraphStore,
        retriever: GraphRetriever | None = None,
    ) -> None:
        self._rag = rag_retrieval_service
        self._store = graph_store
        self._retriever = retriever or GraphRetriever(graph_store)

    async def search(self, request: GraphRAGRequest) -> GraphRAGResult:
        vector_matches = await self._rag.retrieve(
            RetrievalRequest(
                query=request.query,
                top_k=request.top_k_vector,
                source_ids=request.source_ids,
                source_urls=request.source_urls,
            )
        )

        seeds = await self._find_seed_nodes(request.query)
        graph_matches = await self._expand_seeds(
            seeds,
            limit=request.top_k_graph,
        )
        graph_paths = await self._seed_paths(
            seeds,
            max_depth=request.max_path_depth,
        )

        merged = self._merge_context(
            vector_matches,
            graph_matches,
            limit=request.merged_context_limit,
        )
        provenance = self._collect_provenance(merged, graph_paths)
        return GraphRAGResult(
            query=request.query,
            vector_matches=vector_matches,
            graph_matches=list(graph_matches.values()),
            graph_paths=graph_paths,
            merged_context=merged,
            provenance=provenance,
        )

    async def _find_seed_nodes(self, query: str) -> list[GraphNode]:
        tokens = self._query_tokens(query)
        seeds: dict[str, GraphNode] = {}
        for token in tokens:
            for node in await self._store.find_nodes(
                label=token,
                limit=20,
            ):
                seeds.setdefault(node.node_id, node)
        return list(seeds.values())

    async def _expand_seeds(
        self,
        seeds: list[GraphNode],
        *,
        limit: int,
    ) -> dict[str, GraphNode]:
        matches: dict[str, GraphNode] = {}
        for seed in seeds[:20]:
            matches.setdefault(seed.node_id, seed)
            neighbors = await self._retriever.expand(
                seed.node_id,
                limit=50,
            )
            for neighbor in neighbors:
                matches.setdefault(neighbor.node.node_id, neighbor.node)
        ordered = sorted(
            matches.values(),
            key=lambda node: self._node_score(node),
            reverse=True,
        )
        return {node.node_id: node for node in ordered[:limit]}

    async def _seed_paths(
        self,
        seeds: list[GraphNode],
        *,
        max_depth: int,
    ) -> list[object]:
        entity_seeds = [
            node
            for node in seeds
            if node.node_type.value in self._ENTITY_TYPES
        ]
        paths: list[object] = []
        for left_index, left in enumerate(entity_seeds):
            for right in entity_seeds[left_index + 1 :]:
                found = await self._store.find_paths(
                    left.node_id,
                    right.node_id,
                    max_depth=max_depth,
                    limit=2,
                )
                paths.extend(found)
                if len(paths) >= self._MAX_PATHS:
                    return paths
        return paths

    def _merge_context(
        self,
        vector_matches,
        graph_matches: dict[str, GraphNode],
        *,
        limit: int,
    ) -> list[GraphRAGContextItem]:
        items: list[GraphRAGContextItem] = []
        for match in vector_matches:
            items.append(
                GraphRAGContextItem(
                    kind="vector",
                    text=match.text,
                    source_id=match.source_id,
                    source_url=match.source_url,
                    score=match.similarity_score,
                    provenance=[
                        GraphProvenance(
                            source_id=match.source_id,
                            url=str(match.source_url),
                            description="vector similarity retrieval",
                        )
                    ],
                )
            )
        for node in graph_matches.values():
            items.append(self._node_context_item(node))

        unique: dict[tuple[str, str], GraphRAGContextItem] = {}
        for item in items:
            key = (item.kind, item.text.casefold())
            existing = unique.get(key)
            if existing is None or item.score > existing.score:
                unique[key] = item
        ranked = sorted(
            unique.values(),
            key=lambda item: item.score,
            reverse=True,
        )
        return ranked[:limit]

    def _node_context_item(self, node: GraphNode) -> GraphRAGContextItem:
        node_type = node.node_type.value
        if node_type == "evidence":
            kind = "evidence"
            score = self._STRENGTH_SCORES.get(
                node.metadata.get("strength", "unknown"),
                0.7,
            )
        elif node_type == "claim":
            kind = "claim"
            score = 0.6
        elif node_type == "source":
            kind = "source"
            score = 0.5
        else:
            kind = "entity"
            score = 0.4
        return GraphRAGContextItem(
            kind=kind,
            text=node.label,
            node_id=node.node_id,
            node_type=node_type,
            score=score,
            provenance=node.provenance,
        )

    def _collect_provenance(self, merged, graph_paths) -> list[GraphProvenance]:
        provenance: dict[
            tuple[str, str, str, str], GraphProvenance
        ] = {}
        for item in merged:
            for reference in item.provenance:
                self._index_provenance(provenance, reference)
        for path in graph_paths:
            for edge in path.edges:
                for reference in edge.provenance:
                    self._index_provenance(provenance, reference)
        ordered = sorted(
            provenance.values(),
            key=lambda reference: (
                reference.source_id or "",
                reference.evidence_id or "",
                reference.url or "",
                reference.description or "",
            ),
        )
        return ordered[:100]

    @staticmethod
    def _index_provenance(
        index: dict[tuple[str, str, str, str], GraphProvenance],
        reference: GraphProvenance,
    ) -> None:
        key = (
            reference.source_id or "",
            reference.evidence_id or "",
            reference.url or "",
            reference.description or "",
        )
        index.setdefault(key, reference)

    @staticmethod
    def _query_tokens(query: str) -> list[str]:
        tokens = re.findall(r"[A-Za-z0-9]+", query.casefold())
        return [token for token in tokens if len(token) >= 3]

    def _node_score(self, node: GraphNode) -> float:
        node_type = node.node_type.value
        if node_type == "evidence":
            return self._STRENGTH_SCORES.get(
                node.metadata.get("strength", "unknown"),
                0.7,
            )
        if node_type == "claim":
            return 0.6
        if node_type == "source":
            return 0.5
        return 0.4
