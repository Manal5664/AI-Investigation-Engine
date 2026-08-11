from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.core.exceptions import ApplicationError
from app.documents.models import (
    ExtractedDocument,
    StoredDocument,
    UploadedDocument,
)


class DocumentValidationError(ApplicationError):
    """Reject unsupported, malformed, or oversized document uploads."""

    def __init__(self, message: str, *, status_code: int = 422) -> None:
        super().__init__(
            message,
            code="document_validation_error",
            status_code=status_code,
        )


class DocumentExtractionError(ApplicationError):
    """Signal a structurally valid file that could not be extracted."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            code="document_extraction_error",
            status_code=422,
        )


class DocumentExtractor(ABC):
    """Extract normalized, page-preserving content from a validated upload."""

    @property
    @abstractmethod
    def kind(self) -> str:
        """Return the document kind this extractor handles."""

    @abstractmethod
    async def extract(
        self,
        uploaded: UploadedDocument,
        content: bytes,
        *,
        max_pages: int,
    ) -> ExtractedDocument:
        """Extract typed content without executing any uploaded material."""


class DocumentStore(ABC):
    @property
    @abstractmethod
    def store_name(self) -> str:
        """Return a stable identifier for the store backend."""

    @abstractmethod
    async def save(self, stored: StoredDocument) -> None:
        """Persist an uploaded document and its extracted content."""

    @abstractmethod
    async def get(self, document_id: str) -> StoredDocument | None:
        """Return a stored document by ID or None."""

    @abstractmethod
    async def get_many(
        self,
        document_ids: Sequence[str],
    ) -> list[StoredDocument]:
        """Return stored documents for the supplied IDs, preserving order."""

    @abstractmethod
    async def contains_hash(self, content_hash: str) -> bool:
        """Return whether a document with the given content hash exists."""

    @abstractmethod
    async def list_all(
        self,
        *,
        kind: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StoredDocument]:
        """Return stored documents ordered by upload time."""

    @abstractmethod
    async def delete(self, document_id: str) -> bool:
        """Remove a stored document; return False when it did not exist."""

    @abstractmethod
    async def stats(self) -> object:
        """Return store statistics."""

    @abstractmethod
    async def clear(self) -> int:
        """Remove all stored documents and return how many were removed."""


__all__ = [
    "DocumentExtractionError",
    "DocumentExtractor",
    "DocumentStore",
    "DocumentValidationError",
]
