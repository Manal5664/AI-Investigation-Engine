"""Semantic search over stored documents at page granularity.

Document pages are indexed into the shared vector store using synthetic
source records so that pages can be recalled by an ordinary semantic
retrieval request and mapped back to (document_id, page_number).
"""

from dataclasses import dataclass, field

from app.documents.base import DocumentStore
from app.rag.chunking import DocumentChunker
from app.rag.embeddings.base import EmbeddingProvider
from app.rag.vectorstore.base import VectorStore
from app.schemas.rag import (
    IndexSource,
    RetrievalResult,
)

DOCUMENT_SOURCE_URL_TEMPLATE = "https://documents.example.com/{document_id}"
DOCUMENT_LOCATION_PREFIX = "page:"


@dataclass(frozen=True)
class RelevantPage:
    document_id: str
    page_number: int
    score: float = 0.0


@dataclass(frozen=True)
class DocumentPageIndexResult:
    document_id: str
    pages_indexed: int = 0
    chunks_created: int = 0
    duplicates_skipped: int = 0
    failures: list[str] = field(default_factory=list)


def page_location(page_number: int) -> str:
    return f"{DOCUMENT_LOCATION_PREFIX}{page_number}"


def parse_page_location(location: str | None) -> int | None:
    if not location or not location.startswith(DOCUMENT_LOCATION_PREFIX):
        return None
    suffix = location[len(DOCUMENT_LOCATION_PREFIX):]
    return int(suffix) if suffix.isdigit() else None


def document_source_url(document_id: str) -> str:
    return DOCUMENT_SOURCE_URL_TEMPLATE.format(document_id=document_id)


class DocumentRAGService:
    """Index and retrieve stored document pages through the vector store."""

    def __init__(
        self,
        document_store: DocumentStore,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        *,
        chunk_size: int | None = None,
        overlap: int | None = None,
        top_k: int = 10,
    ) -> None:
        self._document_store = document_store
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._top_k = top_k

    @property
    def rag_available(self) -> bool:
        return self._embedding_provider is not None and self._vector_store is not None

    async def index_document(
        self,
        document_id: str,
    ) -> DocumentPageIndexResult | None:
        """Index every extracted page of a document; return None if RAG is off."""
        if not self.rag_available:
            return None
        stored = await self._document_store.get(document_id)
        if stored is None:
            return None

        pages_indexed = 0
        chunks_created = 0
        duplicates_skipped = 0
        failures: list[str] = []
        for page in stored.extracted.pages:
            text = page.text.strip()
            if not text:
                continue
            source = IndexSource(
                source_id=stored.uploaded.document_id,
                source_url=document_source_url(stored.uploaded.document_id),
                title=(
                    f"{stored.uploaded.filename} page {page.page_number}"
                ),
                content=text,
                section=None,
                location=page_location(page.page_number),
            )
            chunker = DocumentChunker(
                chunk_size=self._chunk_size or 1000,
                overlap=min(self._overlap or 150, 999),
            )
            try:
                chunks = chunker.chunk(source)
                vectors = await self._embedding_provider.embed_texts(
                    [chunk.text for chunk in chunks]
                )
                write_result = await self._vector_store.add_chunks(
                    chunks,
                    vectors,
                )
            except Exception as exc:
                failures.append(
                    f"page {page.page_number}: {type(exc).__name__}"
                )
                continue

            pages_indexed += 1
            chunks_created += write_result.added_count
            duplicates_skipped += write_result.duplicates_skipped

        return DocumentPageIndexResult(
            document_id=document_id,
            pages_indexed=pages_indexed,
            chunks_created=chunks_created,
            duplicates_skipped=duplicates_skipped,
            failures=failures,
        )

    async def find_relevant_pages(
        self,
        query: str,
        *,
        limit: int = 5,
        document_ids: list[str] | None = None,
    ) -> list[RelevantPage]:
        """Return the most relevant (document_id, page_number) pairs."""
        if not self.rag_available:
            return []
        query_vector = await self._embedding_provider.embed_text(query)
        results = await self._vector_store.similarity_search(
            query_vector=query_vector,
            top_k=self._top_k,
            source_ids=set(document_ids) if document_ids else None,
            source_urls=None,
        )
        if not results:
            return []

        pages: dict[tuple[str, int], float] = {}
        for result in results:
            page_number = parse_page_location(result.metadata.location)
            if page_number is None:
                continue
            key = (result.source_id, page_number)
            pages[key] = max(pages.get(key, -1.0), result.similarity_score)

        ordered = sorted(
            pages.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        return [
            RelevantPage(
                document_id=document_id,
                page_number=page_number,
                score=score,
            )
            for (document_id, page_number), score in ordered[:limit]
        ]

    async def index_all(
        self,
        document_ids: list[str] | None = None,
    ) -> list[DocumentPageIndexResult]:
        """Index all stored documents (or a subset) and report per-doc results."""
        if not self.rag_available:
            return []
        targets = document_ids
        if targets is None:
            stored_documents = await self._document_store.list_all(limit=1000)
            targets = [
                stored.uploaded.document_id
                for stored in stored_documents
            ]
        results: list[DocumentPageIndexResult] = []
        for document_id in targets:
            result = await self.index_document(document_id)
            if result is not None:
                results.append(result)
        return results


__all__ = [
    "DOCUMENT_SOURCE_URL_TEMPLATE",
    "DocumentPageIndexResult",
    "DocumentRAGService",
    "RelevantPage",
    "document_source_url",
    "page_location",
    "parse_page_location",
]
