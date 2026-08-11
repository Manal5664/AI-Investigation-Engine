"""In-memory repository implementations used as the test/development fallback."""

from __future__ import annotations

from app.database.repositories.base import (
    DocumentRepository,
    DuplicateDocumentHashError,
    DuplicateResourceError,
    EvidenceRepository,
    InvestigationRepository,
    SourceRepository,
    UserRepository,
)
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


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, UserRecord] = {}
        self._by_email: dict[str, UserRecord] = {}

    def create(self, record: UserRecord) -> UserRecord:
        if record.email.casefold() in self._by_email:
            raise DuplicateResourceError(
                f"a user with email {record.email!r} already exists"
            )
        self._by_id[record.id] = record
        self._by_email[record.email.casefold()] = record
        return record

    def get(self, user_id: str) -> UserRecord | None:
        return self._by_id.get(user_id)

    def get_by_email(self, email: str) -> UserRecord | None:
        return self._by_email.get(email.casefold())

    def list(self, *, limit: int, offset: int) -> list[UserRecord]:
        ordered = sorted(
            self._by_id.values(),
            key=lambda record: (record.created_at, record.id),
        )
        return ordered[offset:offset + limit]

    def count(self) -> int:
        return len(self._by_id)

    def delete(self, user_id: str) -> bool:
        record = self._by_id.pop(user_id, None)
        if record is None:
            return False
        self._by_email.pop(record.email.casefold(), None)
        return True

    def clear(self) -> int:
        count = len(self._by_id)
        self._by_id.clear()
        self._by_email.clear()
        return count


class InMemoryInvestigationRepository(InvestigationRepository):
    def __init__(
        self,
        *,
        sources: SourceRepository | None = None,
        evidence: EvidenceRepository | None = None,
    ) -> None:
        self._by_id: dict[str, InvestigationRecord] = {}
        self._steps: dict[str, list[InvestigationStepRecord]] = {}
        self._conflicts: dict[str, list[ConflictRecord]] = {}
        self._reports: dict[str, InvestigationReportRecord] = {}
        self._sources = sources
        self._evidence = evidence

    def create(self, record: InvestigationRecord) -> InvestigationRecord:
        if record.id in self._by_id:
            raise DuplicateResourceError(
                f"investigation {record.id!r} already exists"
            )
        self._by_id[record.id] = record
        return record

    def get(self, investigation_id: str) -> InvestigationRecord | None:
        return self._by_id.get(investigation_id)

    def get_detail(
        self,
        investigation_id: str,
    ) -> InvestigationDetailRecord | None:
        record = self.get(investigation_id)
        if record is None:
            return None
        return InvestigationDetailRecord(
            investigation=record,
            steps=list(self._steps.get(investigation_id, [])),
            sources=(
                self._sources.list_for_investigation(investigation_id)
                if self._sources is not None
                else []
            ),
            evidence_items=(
                self._evidence.list_for_investigation(investigation_id)
                if self._evidence is not None
                else []
            ),
            conflicts=list(self._conflicts.get(investigation_id, [])),
            report=self._reports.get(investigation_id),
        )

    def list(self, *, limit: int, offset: int) -> list[InvestigationRecord]:
        ordered = sorted(
            self._by_id.values(),
            key=lambda record: (record.created_at, record.id),
            reverse=True,
        )
        return ordered[offset:offset + limit]

    def count(self) -> int:
        return len(self._by_id)

    def delete(self, investigation_id: str) -> bool:
        if investigation_id not in self._by_id:
            return False
        self._by_id.pop(investigation_id)
        self._steps.pop(investigation_id, None)
        self._conflicts.pop(investigation_id, None)
        self._reports.pop(investigation_id, None)
        if self._sources is not None:
            self._sources.save_many(investigation_id, [])
        if self._evidence is not None:
            self._evidence.save_items(investigation_id, [])
        return True

    def save_steps(
        self,
        investigation_id: str,
        steps: list[InvestigationStepRecord],
    ) -> None:
        self._steps[investigation_id] = list(steps)

    def list_steps(
        self,
        investigation_id: str,
    ) -> list[InvestigationStepRecord]:
        return list(self._steps.get(investigation_id, []))

    def save_conflicts(
        self,
        investigation_id: str,
        conflicts: list[ConflictRecord],
    ) -> None:
        self._conflicts[investigation_id] = list(conflicts)

    def list_conflicts(
        self,
        investigation_id: str,
    ) -> list[ConflictRecord]:
        return list(self._conflicts.get(investigation_id, []))

    def save_report(
        self,
        investigation_id: str,
        report: InvestigationReportRecord,
    ) -> None:
        self._reports[investigation_id] = report

    def get_report(
        self,
        investigation_id: str,
    ) -> InvestigationReportRecord | None:
        return self._reports.get(investigation_id)

    def clear(self) -> int:
        count = len(self._by_id)
        self._by_id.clear()
        self._steps.clear()
        self._conflicts.clear()
        self._reports.clear()
        return count


class InMemoryDocumentRepository(DocumentRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, StoredDocument] = {}

    def save(self, stored: StoredDocument) -> None:
        if any(
            item.uploaded.content_hash == stored.uploaded.content_hash
            for item in self._by_id.values()
            if item.uploaded.document_id != stored.uploaded.document_id
        ):
            raise DuplicateDocumentHashError(
                f"a document with hash {stored.uploaded.content_hash!r} "
                "already exists"
            )
        self._by_id[stored.uploaded.document_id] = stored

    def get(self, document_id: str) -> StoredDocument | None:
        return self._by_id.get(document_id)

    def find_by_hash(self, content_hash: str) -> StoredDocument | None:
        for stored in self._by_id.values():
            if stored.uploaded.content_hash == content_hash:
                return stored
        return None

    def list(
        self,
        *,
        limit: int,
        offset: int,
        kind: str | None = None,
    ) -> list[StoredDocument]:
        ordered = sorted(
            self._by_id.values(),
            key=lambda stored: (
                stored.uploaded.received_at,
                stored.uploaded.document_id,
            ),
            reverse=True,
        )
        if kind is not None:
            ordered = [
                stored
                for stored in ordered
                if stored.uploaded.kind.value == kind
            ]
        return ordered[offset:offset + limit]

    def count(self, *, kind: str | None = None) -> int:
        if kind is None:
            return len(self._by_id)
        return sum(
            1
            for stored in self._by_id.values()
            if stored.uploaded.kind.value == kind
        )

    def delete(self, document_id: str) -> bool:
        return self._by_id.pop(document_id, None) is not None

    def clear(self) -> int:
        count = len(self._by_id)
        self._by_id.clear()
        return count


class InMemorySourceRepository(SourceRepository):
    def __init__(self) -> None:
        self._by_investigation: dict[str, list[SourceRecord]] = {}

    def save_many(
        self,
        investigation_id: str,
        sources: list[SourceRecord],
    ) -> None:
        self._by_investigation[investigation_id] = list(sources)

    def list_for_investigation(
        self,
        investigation_id: str,
    ) -> list[SourceRecord]:
        return list(self._by_investigation.get(investigation_id, []))

    def clear(self) -> int:
        count = sum(len(items) for items in self._by_investigation.values())
        self._by_investigation.clear()
        return count


class InMemoryEvidenceRepository(EvidenceRepository):
    def __init__(self) -> None:
        self._by_investigation: dict[str, list[EvidenceItemRecord]] = {}

    def save_items(
        self,
        investigation_id: str,
        items: list[EvidenceItemRecord],
    ) -> None:
        self._by_investigation[investigation_id] = list(items)

    def list_for_investigation(
        self,
        investigation_id: str,
    ) -> list[EvidenceItemRecord]:
        return list(self._by_investigation.get(investigation_id, []))

    def clear(self) -> int:
        count = sum(len(items) for items in self._by_investigation.values())
        self._by_investigation.clear()
        return count


__all__ = [
    "InMemoryDocumentRepository",
    "InMemoryEvidenceRepository",
    "InMemoryInvestigationRepository",
    "InMemorySourceRepository",
    "InMemoryUserRepository",
]
