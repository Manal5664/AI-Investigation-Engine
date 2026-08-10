from app.graph.base import GraphStore
from app.graph.models import (
    GraphNeighbor,
    GraphNode,
    GraphPath,
    GraphRelationType,
)


class GraphRetriever:
    """Convenience queries over a provider-neutral graph store."""

    def __init__(self, graph_store: GraphStore) -> None:
        self._store = graph_store

    async def entities_related_to_claim(
        self,
        claim_node_id: str,
        *,
        limit: int = 20,
    ) -> list[GraphNode]:
        entities: list[GraphNode] = []
        seen: set[str] = set()
        cited_sources = await self._store.get_neighbors(
            claim_node_id,
            relation_type=GraphRelationType.CITES.value,
            direction="out",
            limit=limit * 5,
        )
        for neighbor in cited_sources:
            mentioned = await self._store.get_neighbors(
                neighbor.node.node_id,
                relation_type=GraphRelationType.MENTIONS.value,
                direction="out",
                limit=limit * 2,
            )
            for item in mentioned:
                if item.node.node_id in seen:
                    continue
                seen.add(item.node.node_id)
                entities.append(item.node)
        return entities[:limit]

    async def strongest_evidence_for_source(
        self,
        source_node_id: str,
        *,
        limit: int = 20,
    ) -> list[GraphNode]:
        neighbors = await self._store.get_neighbors(
            source_node_id,
            relation_type=GraphRelationType.DERIVED_FROM.value,
            direction="in",
            limit=limit * 5,
        )
        return self._sort_by_confidence(neighbors)[:limit]

    async def contradicting_evidence_for_claim(
        self,
        claim_node_id: str,
        *,
        limit: int = 20,
    ) -> list[GraphNode]:
        neighbors = await self._store.get_neighbors(
            claim_node_id,
            relation_type=GraphRelationType.CONTRADICTS.value,
            direction="in",
            limit=limit * 5,
        )
        return self._sort_by_confidence(neighbors)[:limit]

    async def sources_mentioning(
        self,
        *,
        node_id: str | None = None,
        label: str | None = None,
        limit: int = 20,
    ) -> list[GraphNode]:
        source_nodes: list[GraphNode] = []
        seen: set[str] = set()
        if node_id is not None:
            mentions = await self._store.get_neighbors(
                node_id,
                relation_type=GraphRelationType.MENTIONS.value,
                direction="in",
                limit=limit * 5,
            )
            for item in mentions:
                if item.node.node_id in seen:
                    continue
                seen.add(item.node.node_id)
                source_nodes.append(item.node)
        if label is not None:
            for entity in await self._store.find_nodes(
                node_type=None,
                label=label,
                limit=limit * 2,
            ):
                mentions = await self._store.get_neighbors(
                    entity.node_id,
                    relation_type=GraphRelationType.MENTIONS.value,
                    direction="in",
                    limit=limit * 5,
                )
                for item in mentions:
                    if item.node.node_id in seen:
                        continue
                    seen.add(item.node.node_id)
                    source_nodes.append(item.node)
        return source_nodes[:limit]

    async def paths_between(
        self,
        start_node_id: str,
        end_node_id: str,
        *,
        max_depth: int = 5,
        limit: int = 5,
    ) -> list[GraphPath]:
        return await self._store.find_paths(
            start_node_id,
            end_node_id,
            max_depth=max_depth,
            limit=limit,
        )

    async def nodes_matching(
        self,
        *,
        label: str,
        node_type: str | None = None,
        limit: int = 20,
    ) -> list[GraphNode]:
        return await self._store.find_nodes(
            node_type=node_type,
            label=label,
            limit=limit,
        )

    async def expand(
        self,
        node_id: str,
        *,
        relation_type: str | None = None,
        direction: str = "both",
        limit: int = 100,
    ) -> list[GraphNeighbor]:
        return await self._store.get_neighbors(
            node_id,
            relation_type=relation_type,
            direction=direction,
            limit=limit,
        )

    @staticmethod
    def _sort_by_confidence(
        neighbors: list[GraphNeighbor],
    ) -> list[GraphNode]:
        ranked = sorted(
            neighbors,
            key=lambda item: (
                item.edge.confidence if item.edge.confidence is not None else 0.0
            ),
            reverse=True,
        )
        return [item.node for item in ranked]
