"""In-memory store for uploaded documents and their extracted content."""

import asyncio
from collections import defaultdict
from collections.abc import Sequence

from app.documents.base import DocumentStore
from app.documents.models import (
    DocumentKind,
    DocumentStoreStats,
    StoredDocument,
)


class InMemoryDocumentStore(DocumentStore):
    """Keep all documents in memory; use InMemoryDocumentStore.clear() at shutdown.

    Do not use this store for production workloads that need durable
    persistence.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._documents: dict[str, StoredDocument] = {}

    @property
    def store_name(self) -> str:
        return "in_memory"

    async def save(self, stored: StoredDocument) -> None:
        async with self._lock:
            self._documents[stored.uploaded.document_id] = stored

    async def get(self, document_id: str) -> StoredDocument | None:
        async with self._lock:
            return self._documents.get(document_id)

    async def get_many(
        self,
        document_ids: Sequence[str],
    ) -> list[StoredDocument]:
        if not document_ids:
            return []
        async with self._lock:
            found: list[StoredDocument] = []
            for document_id in document_ids:
                stored = self._documents.get(document_id)
                if stored is not None:
                    found.append(stored)
            return found

    async def contains_hash(self, content_hash: str) -> bool:
        async with self._lock:
            return any(
                stored.uploaded.content_hash == content_hash
                for stored in self._documents.values()
            )

    async def list_all(
        self,
        *,
        kind: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StoredDocument]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        if offset < 0:
            raise ValueError("offset must not be negative")
        async with self._lock:
            documents = sorted(
                self._documents.values(),
                key=lambda stored: stored.uploaded.received_at,
                reverse=True,
            )
            if kind is not None:
                documents = [
                    stored
                    for stored in documents
                    if stored.uploaded.kind.value == kind
                ]
            return documents[offset:offset + limit]

    async def delete(self, document_id: str) -> bool:
        async with self._lock:
            return self._documents.pop(document_id, None) is not None

    async def stats(self) -> DocumentStoreStats:
        async with self._lock:
            counts_by_kind: dict[str, int] = defaultdict(int)
            for stored in self._documents.values():
                counts_by_kind[stored.uploaded.kind.value] += 1
            total_bytes = sum(
                stored.uploaded.file_size_bytes
                for stored in self._documents.values()
            )
            return DocumentStoreStats(
                store_type=self.store_name,
                document_count=len(self._documents),
                total_bytes=total_bytes,
                counts_by_kind=dict(counts_by_kind),
            )

    async def clear(self) -> int:
        async with self._lock:
            count = len(self._documents)
            self._documents.clear()
            return count


__all__ = ["InMemoryDocumentStore"]
