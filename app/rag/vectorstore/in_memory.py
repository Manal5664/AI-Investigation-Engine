import asyncio
import math
from collections.abc import Sequence
from dataclasses import dataclass

from app.rag.vectorstore.base import (
    VectorStore,
    VectorStoreAddResult,
    cosine_similarity,
)
from app.schemas.rag import (
    DocumentChunk,
    RetrievalResult,
    VectorStoreStats,
)


@dataclass(frozen=True, slots=True)
class _VectorRecord:
    chunk: DocumentChunk
    vector: tuple[float, ...]


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._records: dict[str, _VectorRecord] = {}
        self._content_keys: set[tuple[str, str, str]] = set()
        self._vector_dimension: int | None = None
        self._lock = asyncio.Lock()

    @property
    def store_name(self) -> str:
        return "in_memory"

    async def add_chunks(
        self,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[Sequence[float]],
    ) -> VectorStoreAddResult:
        if len(chunks) != len(vectors):
            raise ValueError("Each chunk must have exactly one vector")
        validated_vectors = [self._validate_vector(vector) for vector in vectors]

        async with self._lock:
            expected_dimension = self._vector_dimension
            for vector in validated_vectors:
                if expected_dimension is None:
                    expected_dimension = len(vector)
                elif len(vector) != expected_dimension:
                    raise ValueError(
                        "Vector dimension does not match the store dimension"
                    )

            pending_ids: set[str] = set()
            pending_content: set[tuple[str, str, str]] = set()
            additions: list[tuple[DocumentChunk, tuple[float, ...]]] = []
            duplicates = 0
            for chunk, vector in zip(chunks, validated_vectors):
                content_key = self._content_key(chunk)
                if (
                    chunk.chunk_id in self._records
                    or chunk.chunk_id in pending_ids
                    or content_key in self._content_keys
                    or content_key in pending_content
                ):
                    duplicates += 1
                    continue
                pending_ids.add(chunk.chunk_id)
                pending_content.add(content_key)
                additions.append((chunk, vector))

            for chunk, vector in additions:
                self._records[chunk.chunk_id] = _VectorRecord(
                    chunk=chunk,
                    vector=vector,
                )
                self._content_keys.add(self._content_key(chunk))
            if additions:
                self._vector_dimension = len(additions[0][1])

        return VectorStoreAddResult(
            added_count=len(additions),
            duplicates_skipped=duplicates,
        )

    async def similarity_search(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int,
        source_ids: set[str] | None = None,
        source_urls: set[str] | None = None,
    ) -> list[RetrievalResult]:
        if top_k <= 0:
            raise ValueError("top_k must be greater than zero")
        vector = self._validate_vector(query_vector)
        normalized_urls = (
            {str(url) for url in source_urls}
            if source_urls is not None
            else None
        )

        async with self._lock:
            if not self._records:
                return []
            if len(vector) != self._vector_dimension:
                raise ValueError(
                    "Query vector dimension does not match the store dimension"
                )
            records = list(self._records.values())

        scored: list[tuple[float, DocumentChunk]] = []
        for record in records:
            chunk = record.chunk
            if source_ids is not None and chunk.source_id not in source_ids:
                continue
            if (
                normalized_urls is not None
                and str(chunk.source_url) not in normalized_urls
            ):
                continue
            scored.append(
                (cosine_similarity(vector, record.vector), chunk)
            )
        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        return [
            RetrievalResult(
                chunk_id=chunk.chunk_id,
                source_id=chunk.source_id,
                source_url=chunk.source_url,
                text=chunk.text,
                similarity_score=score,
                metadata=chunk.metadata,
            )
            for score, chunk in scored[:top_k]
        ]

    async def delete_by_source(self, source_id: str) -> int:
        normalized_id = source_id.strip()
        if not normalized_id:
            raise ValueError("source_id must not be empty")
        async with self._lock:
            chunk_ids = [
                chunk_id
                for chunk_id, record in self._records.items()
                if record.chunk.source_id == normalized_id
            ]
            for chunk_id in chunk_ids:
                record = self._records.pop(chunk_id)
                self._content_keys.discard(
                    self._content_key(record.chunk)
                )
            if not self._records:
                self._vector_dimension = None
            return len(chunk_ids)

    async def clear(self) -> int:
        async with self._lock:
            removed = len(self._records)
            self._records.clear()
            self._content_keys.clear()
            self._vector_dimension = None
            return removed

    async def count(self) -> int:
        async with self._lock:
            return len(self._records)

    async def stats(self) -> VectorStoreStats:
        async with self._lock:
            sources = {
                (record.chunk.source_id, str(record.chunk.source_url))
                for record in self._records.values()
            }
            return VectorStoreStats(
                store_type=self.store_name,
                vector_count=len(self._records),
                source_count=len(sources),
                vector_dimension=self._vector_dimension,
            )

    @staticmethod
    def _validate_vector(vector: Sequence[float]) -> tuple[float, ...]:
        if not vector:
            raise ValueError("Vectors must not be empty")
        normalized = tuple(float(value) for value in vector)
        if not all(math.isfinite(value) for value in normalized):
            raise ValueError("Vectors must contain only finite values")
        return normalized

    @staticmethod
    def _content_key(chunk: DocumentChunk) -> tuple[str, str, str]:
        return (
            chunk.source_id,
            str(chunk.source_url),
            chunk.metadata.content_hash,
        )
