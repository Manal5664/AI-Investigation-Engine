"""Provider-neutral repository abstractions for persisted entities.

Repositories speak domain types (``StoredDocument``, ``UserRecord``,
``InvestigationRecord``, ...) so services and routes never depend on a
specific backend. SQLAlchemy and in-memory implementations both satisfy
these interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.documents.models import StoredDocument
from app.schemas.persistence import (
    ConflictRecord,
    EvidenceItemRecord,
    InvestigationDetailRecord,
    InvestigationRecord,
    InvestigationReportRecord,
    InvestigationStepRecord,
    SourceRecord,
    UserRecord,
)


class PersistenceError(Exception):
    """Base class for repository-level persistence failures."""


class DuplicateResourceError(PersistenceError):
    """A unique domain key (e.g. content hash or email) already exists."""


class DuplicateDocumentHashError(DuplicateResourceError):
    """A document with the same SHA-256 content hash already exists."""


class UserRepository(ABC):
    @abstractmethod
    def create(self, record: UserRecord) -> UserRecord:
        """Persist a new user; raise DuplicateResourceError on email clash."""

    @abstractmethod
    def get(self, user_id: str) -> UserRecord | None:
        """Return a user by ID, or None."""

    @abstractmethod
    def get_by_email(self, email: str) -> UserRecord | None:
        """Return a user by email, or None."""

    @abstractmethod
    def list(self, *, limit: int, offset: int) -> list[UserRecord]:
        """Return users ordered by creation time."""

    @abstractmethod
    def count(self) -> int:
        """Return the total number of users."""

    @abstractmethod
    def delete(self, user_id: str) -> bool:
        """Delete a user; return False when it did not exist."""

    @abstractmethod
    def clear(self) -> int:
        """Delete all users; return how many were removed."""


class InvestigationRepository(ABC):
    @abstractmethod
    def create(self, record: InvestigationRecord) -> InvestigationRecord:
        """Persist the investigation header row."""

    @abstractmethod
    def get(self, investigation_id: str) -> InvestigationRecord | None:
        """Return an investigation header, or None."""

    @abstractmethod
    def get_detail(
        self,
        investigation_id: str,
    ) -> InvestigationDetailRecord | None:
        """Return an investigation with steps, sources, evidence, report."""

    @abstractmethod
    def list(self, *, limit: int, offset: int) -> list[InvestigationRecord]:
        """Return investigations ordered by creation time (newest first)."""

    @abstractmethod
    def count(self) -> int:
        """Return the total number of investigations."""

    @abstractmethod
    def delete(self, investigation_id: str) -> bool:
        """Delete an investigation and its children; return whether it existed."""

    @abstractmethod
    def save_steps(
        self,
        investigation_id: str,
        steps: list[InvestigationStepRecord],
    ) -> None:
        """Replace the audit steps for an investigation, preserving order."""

    @abstractmethod
    def list_steps(
        self,
        investigation_id: str,
    ) -> list[InvestigationStepRecord]:
        """Return audit steps in execution order."""

    @abstractmethod
    def save_conflicts(
        self,
        investigation_id: str,
        conflicts: list[ConflictRecord],
    ) -> None:
        """Replace the conflict reports for an investigation."""

    @abstractmethod
    def list_conflicts(
        self,
        investigation_id: str,
    ) -> list[ConflictRecord]:
        """Return conflict reports for an investigation."""

    @abstractmethod
    def save_report(
        self,
        investigation_id: str,
        report: InvestigationReportRecord,
    ) -> None:
        """Replace the synthesis report for an investigation."""

    @abstractmethod
    def get_report(
        self,
        investigation_id: str,
    ) -> InvestigationReportRecord | None:
        """Return the synthesis report for an investigation, or None."""

    @abstractmethod
    def clear(self) -> int:
        """Delete all investigations; return how many were removed."""


class DocumentRepository(ABC):
    @abstractmethod
    def save(self, stored: StoredDocument) -> None:
        """Persist a document and its pages; raise DuplicateDocumentHashError."""

    @abstractmethod
    def get(self, document_id: str) -> StoredDocument | None:
        """Return a stored document by ID, or None."""

    @abstractmethod
    def find_by_hash(self, content_hash: str) -> StoredDocument | None:
        """Return the stored document with this SHA-256, or None."""

    @abstractmethod
    def list(
        self,
        *,
        limit: int,
        offset: int,
        kind: str | None = None,
    ) -> list[StoredDocument]:
        """Return stored documents ordered by upload time (newest first)."""

    @abstractmethod
    def count(self, *, kind: str | None = None) -> int:
        """Return the total number of stored documents."""

    @abstractmethod
    def delete(self, document_id: str) -> bool:
        """Delete a document and its pages; return whether it existed."""

    @abstractmethod
    def clear(self) -> int:
        """Delete all documents; return how many were removed."""


class SourceRepository(ABC):
    @abstractmethod
    def save_many(
        self,
        investigation_id: str,
        sources: list[SourceRecord],
    ) -> None:
        """Replace the sources recorded for an investigation."""

    @abstractmethod
    def list_for_investigation(
        self,
        investigation_id: str,
    ) -> list[SourceRecord]:
        """Return sources for an investigation."""

    @abstractmethod
    def clear(self) -> int:
        """Delete all sources; return how many were removed."""


class EvidenceRepository(ABC):
    @abstractmethod
    def save_items(
        self,
        investigation_id: str,
        items: list[EvidenceItemRecord],
    ) -> None:
        """Replace the evidence items recorded for an investigation."""

    @abstractmethod
    def list_for_investigation(
        self,
        investigation_id: str,
    ) -> list[EvidenceItemRecord]:
        """Return evidence items for an investigation."""

    @abstractmethod
    def clear(self) -> int:
        """Delete all evidence items; return how many were removed."""


__all__ = [
    "DocumentRepository",
    "DuplicateDocumentHashError",
    "DuplicateResourceError",
    "EvidenceRepository",
    "InvestigationRepository",
    "PersistenceError",
    "SourceRepository",
    "UserRepository",
]
