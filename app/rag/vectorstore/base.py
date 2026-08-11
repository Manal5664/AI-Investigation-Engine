import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas.rag import (
    DocumentChunk,
    RetrievalResult,
    VectorStoreStats,
)


@dataclass(frozen=True, slots=True)
class VectorStoreAddResult:
    added_count: int
    duplicates_skipped: int


def cosine_similarity(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    if not left or not right:
        raise ValueError("Cosine similarity requires non-empty vectors")
    if len(left) != len(right):
        raise ValueError("Cosine similarity requires equal dimensions")
    if not all(math.isfinite(float(value)) for value in (*left, *right)):
        raise ValueError("Cosine similarity requires finite values")

    dot_product = sum(
        float(left_value) * float(right_value)
        for left_value, right_value in zip(left, right)
    )
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    score = dot_product / (left_norm * right_norm)
    return max(-1.0, min(1.0, score))


class VectorStore(ABC):
    @property
    @abstractmethod
    def store_name(self) -> str:
        """Return the vector-store implementation identifier."""

    @abstractmethod
    async def add_chunks(
        self,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[Sequence[float]],
    ) -> VectorStoreAddResult:
        """Add chunk/vector pairs without duplicating existing content."""

    @abstractmethod
    async def similarity_search(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int,
        source_ids: set[str] | None = None,
        source_urls: set[str] | None = None,
    ) -> list[RetrievalResult]:
        """Return the highest-cosine matching chunks."""

    @abstractmethod
    async def delete_by_source(self, source_id: str) -> int:
        """Delete all chunks carrying the supplied source ID."""

    @abstractmethod
    async def count_by_source(self, source_id: str) -> int:
        """Return the number of chunks stored for a single source ID."""

    @abstractmethod
    async def clear(self) -> int:
        """Delete every stored vector and return the removed count."""

    @abstractmethod
    async def count(self) -> int:
        """Return the number of stored vectors."""

    @abstractmethod
    async def stats(self) -> VectorStoreStats:
        """Return non-secret in-memory store metadata."""
