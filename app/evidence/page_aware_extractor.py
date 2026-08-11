"""Evidence extraction that can read uploaded documents page by page.

The upstream provider only ever receives normalized text (or a summary of
the content for pages that required vision), never raw byte streams.
"""

from collections.abc import Sequence

from app.documents.base import DocumentStore
from app.evidence.base import EvidenceExtractor
from app.rag.embeddings.base import EmbeddingProvider
from app.rag.vectorstore.base import VectorStore
from app.schemas.evidence import EvidenceItem
from app.schemas.investigation import InvestigationSubQuestion
from app.schemas.source import Source
from app.services.document_rag_service import (
    DocumentRAGService,
    RelevantPage,
)

MAX_CHARACTERS_PER_PAGE = 4000
MAX_PAGES_PER_EVIDENCE_CALL = 8
_DOCUMENT_SOURCE_ID_BASE = 900


class PageAwareEvidenceExtractor(EvidenceExtractor):
    """Combine base evidence extraction with document page awareness."""

    def __init__(
        self,
        base_extractor: EvidenceExtractor,
        document_store: DocumentStore,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._base = base_extractor
        self._document_store = document_store
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    @property
    def provider_name(self) -> str:
        return self._base.provider_name

    @property
    def model_name(self) -> str:
        return self._base.model_name

    async def extract(
        self,
        sub_question: InvestigationSubQuestion,
        sources: Sequence[Source],
        *,
        investigation_query: str | None = None,
    ) -> list[EvidenceItem]:
        combined = list(sources)
        combined.extend(
            await self._document_sources(sub_question, investigation_query)
        )
        if not combined:
            return []
        return await self._base.extract(
            sub_question,
            combined,
            investigation_query=investigation_query,
        )

    async def aclose(self) -> None:
        await self._base.aclose()

    async def _document_sources(
        self,
        sub_question: InvestigationSubQuestion,
        investigation_query: str | None,
    ) -> list[Source]:
        """Convert relevant stored documents into page-granular Source items."""
        rag = DocumentRAGService(
            document_store=self._document_store,
            embedding_provider=self._embedding_provider,
            vector_store=self._vector_store,
        )
        if rag.rag_available:
            page_keys = await rag.find_relevant_pages(
                query=investigation_query or sub_question.question,
                limit=MAX_PAGES_PER_EVIDENCE_CALL,
            )
        else:
            stored_documents = await self._document_store.list_all(limit=100)
            page_keys: list[RelevantPage] = []
            for stored in stored_documents:
                for page in stored.extracted.pages:
                    if not page.text.strip():
                        continue
                    page_keys.append(
                        RelevantPage(
                            document_id=stored.uploaded.document_id,
                            page_number=page.page_number,
                        )
                    )
                    if len(page_keys) >= MAX_PAGES_PER_EVIDENCE_CALL:
                        break
                if len(page_keys) >= MAX_PAGES_PER_EVIDENCE_CALL:
                    break

        sources: list[Source] = []
        for index, key in enumerate(page_keys):
            stored = await self._document_store.get(key.document_id)
            if stored is None:
                continue
            for page in stored.extracted.pages:
                if page.page_number != key.page_number:
                    continue
                if not page.text.strip():
                    continue
                truncated = page.text[:MAX_CHARACTERS_PER_PAGE]
                source_number = _DOCUMENT_SOURCE_ID_BASE + index
                if source_number > 999:
                    continue
                sources.append(
                    Source(
                        source_id=f"source-{source_number}",
                        title=(
                            f"{stored.uploaded.filename} "
                            f"(page {page.page_number})"
                        ),
                        url="https://example.com/document",  # noqa: S105
                        domain="documents",
                        retrieved_at=stored.uploaded.received_at,
                        source_type="unknown",
                        snippet=truncated,
                        metadata={
                            "document_id": stored.uploaded.document_id,
                            "document_filename": stored.uploaded.filename,
                            "document_page": page.page_number,
                        },
                    )
                )
        return sources


__all__ = ["PageAwareEvidenceExtractor"]
