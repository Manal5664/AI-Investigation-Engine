"""Ingestion pipeline that validates, extracts, and stores uploaded files."""

from datetime import datetime, timezone

from app.database.persistence_gateway import DocumentPersistenceGateway
from app.documents.base import DocumentStore, DocumentValidationError
from app.documents.extractors.factory import ExtractorFactory
from app.documents.models import (
    DocumentIngestionResult,
    ExtractedDocument,
    StoredDocument,
    UploadedDocument,
)
from app.documents.validators import validate_upload


class DocumentIngestionService:
    """Validate upload bytes, extract content, and persist results."""

    def __init__(
        self,
        store: DocumentStore,
        extractor_factory: ExtractorFactory,
        *,
        max_bytes: int,
        max_pages: int,
        max_per_request: int,
        document_repository: DocumentPersistenceGateway | None = None,
    ) -> None:
        self._store = store
        self._extractors = extractor_factory
        self._max_bytes = max_bytes
        self._max_pages = max_pages
        self._max_per_request = max_per_request
        self._document_repository = document_repository

    async def ingest(
        self,
        files: list[tuple[str, str, bytes]],
    ) -> list[DocumentIngestionResult]:
        """Ingest (filename, mime_type, content) tuples into the store."""
        if len(files) > self._max_per_request:
            raise DocumentValidationError(
                f"a request may upload at most {self._max_per_request} "
                "documents"
            )

        results: list[DocumentIngestionResult] = []
        for filename, mime_type, content in files:
            validated = validate_upload(
                filename=filename,
                mime_type=mime_type,
                content=content,
                max_bytes=self._max_bytes,
            )
            results.append(await self._ingest_validated(validated))
        return results

    async def _ingest_validated(self, validated) -> DocumentIngestionResult:
        uploaded = validated.uploaded
        if self._document_repository is not None:
            existing = await self._document_repository.find_by_hash(
                uploaded.content_hash
            )
            if existing is not None:
                return self._duplicate_result(existing)
        if await self._store.contains_hash(uploaded.content_hash):
            stored = await self._find_by_hash(uploaded.content_hash)
            if stored is not None:
                return self._duplicate_result(stored)

        extractor = self._extractors.get(uploaded.kind)
        extracted = await extractor.extract(
            uploaded,
            validated.content,
            max_pages=self._max_pages,
        )
        extracted = self._apply_limits(uploaded, extracted)
        stored = StoredDocument(
            uploaded=uploaded,
            extracted=extracted,
            content=validated.content,
        )
        await self._store.save(stored)
        if self._document_repository is not None:
            await self._document_repository.save(stored)
        return DocumentIngestionResult(
            document=uploaded,
            extracted=extracted,
            page_count=extracted.page_count,
            character_count=extracted.character_count,
            duplicate=False,
            warnings=list(extracted.warnings),
        )

    @staticmethod
    def _duplicate_result(stored: StoredDocument) -> DocumentIngestionResult:
        return DocumentIngestionResult(
            document=stored.uploaded,
            extracted=stored.extracted,
            page_count=stored.extracted.page_count,
            character_count=stored.extracted.character_count,
            duplicate=True,
            warnings=["duplicate content; existing document returned"],
        )

    async def _find_by_hash(
        self,
        content_hash: str,
    ) -> StoredDocument | None:
        for stored in await self._store.list_all(limit=1000):
            if stored.uploaded.content_hash == content_hash:
                return stored
        return None

    def _apply_limits(
        self,
        uploaded: UploadedDocument,
        extracted: ExtractedDocument,
    ) -> ExtractedDocument:
        if uploaded.kind.value == "image":
            return extracted
        if extracted.page_count <= self._max_pages:
            return extracted
        if uploaded.kind.value == "pdf":
            truncated = extracted.pages[: self._max_pages]
            return extracted.model_copy(
                update={
                    "pages": truncated,
                    "warnings": list(extracted.warnings)
                    + [
                        f"truncated to {self._max_pages} pages "
                        f"(had {extracted.page_count})"
                    ],
                }
            )
        return extracted


__all__ = ["DocumentIngestionService"]
