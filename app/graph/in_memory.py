import asyncio
from collections import Counter, deque
from typing import Literal

from app.graph.base import GraphStore
from app.graph.models import (
    GraphEdge,
    GraphNeighbor,
    GraphNode,
    GraphPath,
    GraphStats,
)


class InMemoryGraphStore(GraphStore):
    """Process-local graph storage with duplicate prevention."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._edge_keys: set[tuple[str, str, str]] = set()
        self._out_edges: dict[str, list[str]] = {}
        self._in_edges: dict[str, list[str]] = {}
        self._lock = asyncio.Lock()

    @property
    def store_name(self) -> str:
        return "in_memory"

    async def add_node(self, node: GraphNode) -> bool:
        async with self._lock:
            if node.node_id in self._nodes:
                return False
            self._nodes[node.node_id] = node
            return True

    async def add_edge(self, edge: GraphEdge) -> bool:
        async with self._lock:
            if edge.edge_id in self._edges:
                return False
            if edge.source_node_id not in self._nodes:
                raise ValueError(
                    f"Edge source node '{edge.source_node_id}' does not exist."
                )
            if edge.target_node_id not in self._nodes:
                raise ValueError(
                    f"Edge target node '{edge.target_node_id}' does not exist."
                )
            edge_key = (
                edge.source_node_id,
                edge.relation_type.value,
                edge.target_node_id,
            )
            if edge_key in self._edge_keys:
                return False
            self._edges[edge.edge_id] = edge
            self._edge_keys.add(edge_key)
            self._out_edges.setdefault(edge.source_node_id, []).append(
                edge.edge_id
            )
            self._in_edges.setdefault(edge.target_node_id, []).append(
                edge.edge_id
            )
            return True

    async def get_node(self, node_id: str) -> GraphNode | None:
        normalized_id = node_id.strip()
        if not normalized_id:
            raise ValueError("node_id must not be empty")
        async with self._lock:
            return self._nodes.get(normalized_id)

    async def get_neighbors(
        self,
        node_id: str,
        *,
        relation_type: str | None = None,
        direction: Literal["out", "in", "both"] = "both",
        limit: int = 100,
    ) -> list[GraphNeighbor]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        normalized_id = node_id.strip()
        if not normalized_id:
            raise ValueError("node_id must not be empty")
        if direction not in {"out", "in", "both"}:
            raise ValueError("direction must be 'out', 'in', or 'both'")

        async with self._lock:
            if normalized_id not in self._nodes:
                return []
            out_ids = (
                self._out_edges.get(normalized_id, [])
                if direction in {"out", "both"}
                else []
            )
            in_ids = (
                self._in_edges.get(normalized_id, [])
                if direction in {"in", "both"}
                else []
            )

            neighbors: list[GraphNeighbor] = []
            for edge_id in out_ids:
                edge = self._edges[edge_id]
                if (
                    relation_type is not None
                    and edge.relation_type.value != relation_type
                ):
                    continue
                neighbors.append(
                    GraphNeighbor(
                        node=self._nodes[edge.target_node_id],
                        edge=edge,
                        direction="out",
                    )
                )
            for edge_id in in_ids:
                edge = self._edges[edge_id]
                if (
                    relation_type is not None
                    and edge.relation_type.value != relation_type
                ):
                    continue
                neighbors.append(
                    GraphNeighbor(
                        node=self._nodes[edge.source_node_id],
                        edge=edge,
                        direction="in",
                    )
                )
        neighbors.sort(key=lambda item: item.node.node_id)
        return neighbors[:limit]

    async def find_nodes(
        self,
        *,
        node_type: str | None = None,
        label: str | None = None,
        limit: int = 20,
    ) -> list[GraphNode]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        normalized_label = label.strip().casefold() if label else None

        async with self._lock:
            nodes = list(self._nodes.values())
        matches = [
            node
            for node in nodes
            if (
                node_type is None or node.node_type.value == node_type
            )
            and (
                normalized_label is None
                or normalized_label in node.label.casefold()
            )
        ]
        matches.sort(key=lambda node: node.label)
        return matches[:limit]

    async def find_paths(
        self,
        start_node_id: str,
        end_node_id: str,
        *,
        max_depth: int = 5,
        limit: int = 5,
    ) -> list[GraphPath]:
        if max_depth <= 0:
            raise ValueError("max_depth must be greater than zero")
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        start = start_node_id.strip()
        end = end_node_id.strip()
        if not start or not end:
            raise ValueError("start and end node IDs must not be empty")
        if start == end:
            return []

        async with self._lock:
            if start not in self._nodes or end not in self._nodes:
                return []

            adjacency: dict[str, list[GraphEdge]] = {}
            for edge in self._edges.values():
                adjacency.setdefault(edge.source_node_id, []).append(edge)
                adjacency.setdefault(edge.target_node_id, []).append(edge)

            levels: dict[str, int] = {start: 0}
            parent_edges: dict[str, list[GraphEdge]] = {}
            queue = deque([start])
            while queue:
                node = queue.popleft()
                depth = levels[node]
                if depth >= max_depth:
                    continue
                for edge in adjacency.get(node, []):
                    other = (
                        edge.target_node_id
                        if edge.source_node_id == node
                        else edge.source_node_id
                    )
                    next_depth = depth + 1
                    if other in levels and levels[other] < next_depth:
                        continue
                    if other not in levels:
                        levels[other] = next_depth
                        parent_edges[other] = [edge]
                        queue.append(other)
                    elif levels[other] == next_depth:
                        parent_edges[other].append(edge)

            if end not in levels:
                return []

        paths: list[GraphPath] = []

        def backtrack(
            node: str,
            nodes: list[str],
            edges: list[GraphEdge],
        ) -> None:
            if len(paths) >= limit:
                return
            if node == start:
                paths.append(
                    GraphPath(
                        start_node_id=start,
                        end_node_id=end,
                        node_ids=list(reversed(nodes)),
                        edges=list(reversed(edges)),
                    )
                )
                return
            for edge in parent_edges.get(node, []):
                previous = (
                    edge.source_node_id
                    if edge.target_node_id == node
                    else edge.target_node_id
                )
                if previous in nodes:
                    continue
                nodes.append(previous)
                edges.append(edge)
                backtrack(previous, nodes, edges)
                edges.pop()
                nodes.pop()

        backtrack(end, [end], [])
        paths.sort(key=lambda path: len(path.edges))
        return paths[:limit]

    async def delete_investigation(self, investigation_node_id: str) -> int:
        normalized_id = investigation_node_id.strip()
        if not normalized_id:
            raise ValueError("investigation_node_id must not be empty")

        async with self._lock:
            investigation_node = self._nodes.get(normalized_id)
            if investigation_node is None:
                return 0
            investigation_id = investigation_node.metadata.get(
                "investigation_id"
            )
            if not investigation_id:
                return 0

            node_ids = {
                node_id
                for node_id, node in self._nodes.items()
                if node.metadata.get("investigation_id") == investigation_id
            }
            edge_ids = [
                edge_id
                for edge_id, edge in self._edges.items()
                if edge.metadata.get("investigation_id") == investigation_id
            ]
            removed = len(node_ids) + len(edge_ids)

            for edge_id in edge_ids:
                edge = self._edges.pop(edge_id)
                self._edge_keys.discard(
                    (
                        edge.source_node_id,
                        edge.relation_type.value,
                        edge.target_node_id,
                    )
                )
            self._out_edges = {
                node_id: [edge_id for edge_id in ids if edge_id not in edge_ids]
                for node_id, ids in self._out_edges.items()
                if node_id not in node_ids
            }
            self._in_edges = {
                node_id: [edge_id for edge_id in ids if edge_id not in edge_ids]
                for node_id, ids in self._in_edges.items()
                if node_id not in node_ids
            }
            for node_id in node_ids:
                self._nodes.pop(node_id, None)
            return removed

    async def has_document(self, document_id: str) -> bool:
        normalized_id = document_id.strip()
        if not normalized_id:
            raise ValueError("document_id must not be empty")
        async with self._lock:
            return any(
                node.metadata.get("document_id") == normalized_id
                for node in self._nodes.values()
            )

    async def clear(self) -> int:
        async with self._lock:
            removed = len(self._nodes) + len(self._edges)
            self._nodes.clear()
            self._edges.clear()
            self._edge_keys.clear()
            self._out_edges.clear()
            self._in_edges.clear()
            return removed

    async def stats(self) -> GraphStats:
        async with self._lock:
            nodes = list(self._nodes.values())
            edges = list(self._edges.values())
        node_counts = Counter(node.node_type.value for node in nodes)
        edge_counts = Counter(edge.relation_type.value for edge in edges)
        investigation_ids = {
            node.metadata.get("investigation_id")
            for node in nodes
            if node.metadata.get("investigation_id") is not None
        }
        return GraphStats(
            store_type=self.store_name,
            node_count=len(nodes),
            edge_count=len(edges),
            investigation_count=len(investigation_ids),
            counts_by_node_type=dict(sorted(node_counts.items())),
            counts_by_relation_type=dict(sorted(edge_counts.items())),
        )
