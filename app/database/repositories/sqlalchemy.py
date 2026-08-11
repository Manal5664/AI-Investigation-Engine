"""SQLAlchemy implementations of the provider-neutral repository interfaces."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database.mapping import (
    conflict_model_to_record,
    conflict_record_to_model,
    document_model_to_stored,
    evidence_model_to_record,
    evidence_record_to_model,
    investigation_model_to_record,
    investigation_record_to_model,
    report_model_to_record,
    report_record_to_model,
    source_model_to_record,
    source_record_to_model,
    step_model_to_record,
    step_record_to_model,
    stored_document_to_model,
    user_model_to_record,
    user_record_to_model,
)
from app.database.models import (
    Conflict,
    Document,
    EvidenceItem,
    Investigation,
    InvestigationReport,
    InvestigationStep,
    Source,
    User,
)
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


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, record: UserRecord) -> UserRecord:
        if self.get_by_email(record.email) is not None:
            raise DuplicateResourceError(
                f"a user with email {record.email!r} already exists"
            )
        model = user_record_to_model(record)
        self._session.add(model)
        self._flush()
        return record

    def get(self, user_id: str) -> UserRecord | None:
        model = self._session.get(User, user_id)
        return user_model_to_record(model) if model is not None else None

    def get_by_email(self, email: str) -> UserRecord | None:
        model = self._session.scalar(
            select(User).where(User.email == email)
        )
        return user_model_to_record(model) if model is not None else None

    def list(self, *, limit: int, offset: int) -> list[UserRecord]:
        models = list(
            self._session.scalars(
                select(User)
                .order_by(User.created_at.asc(), User.id.asc())
                .limit(limit)
                .offset(offset)
            )
        )
        return [user_model_to_record(model) for model in models]

    def count(self) -> int:
        return int(self._session.scalar(select(func.count()).select_from(User)) or 0)

    def delete(self, user_id: str) -> bool:
        model = self._session.get(User, user_id)
        if model is None:
            return False
        self._session.delete(model)
        self._flush()
        return True

    def clear(self) -> int:
        result = self._session.execute(delete(User))
        self._flush()
        return int(result.rowcount or 0)

    def _flush(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateResourceError(
                "a user with the same identity already exists"
            ) from exc


class SqlAlchemyInvestigationRepository(InvestigationRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, record: InvestigationRecord) -> InvestigationRecord:
        model = investigation_record_to_model(record)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateResourceError(
                f"investigation {record.id!r} already exists"
            ) from exc
        return record

    def get(self, investigation_id: str) -> InvestigationRecord | None:
        model = self._session.get(Investigation, investigation_id)
        return (
            investigation_model_to_record(model)
            if model is not None
            else None
        )

    def get_detail(
        self,
        investigation_id: str,
    ) -> InvestigationDetailRecord | None:
        model = self._session.scalar(
            select(Investigation)
            .where(Investigation.id == investigation_id)
            .options(
                selectinload(Investigation.steps),
                selectinload(Investigation.sources),
                selectinload(Investigation.evidence_items),
                selectinload(Investigation.conflicts),
                selectinload(Investigation.report),
            )
        )
        if model is None:
            return None
        return InvestigationDetailRecord(
            investigation=investigation_model_to_record(model),
            steps=[
                step_model_to_record(step) for step in model.steps
            ],
            sources=[
                source_model_to_record(source) for source in model.sources
            ],
            evidence_items=[
                evidence_model_to_record(item)
                for item in model.evidence_items
            ],
            conflicts=[
                conflict_model_to_record(conflict)
                for conflict in model.conflicts
            ],
            report=(
                report_model_to_record(model.report)
                if model.report is not None
                else None
            ),
        )

    def list(self, *, limit: int, offset: int) -> list[InvestigationRecord]:
        models = list(
            self._session.scalars(
                select(Investigation)
                .order_by(
                    Investigation.created_at.desc(),
                    Investigation.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            )
        )
        return [
            investigation_model_to_record(model) for model in models
        ]

    def count(self) -> int:
        return int(
            self._session.scalar(
                select(func.count()).select_from(Investigation)
            )
            or 0
        )

    def delete(self, investigation_id: str) -> bool:
        model = self._session.get(Investigation, investigation_id)
        if model is None:
            return False
        self._session.delete(model)
        self._flush()
        return True

    def save_steps(
        self,
        investigation_id: str,
        steps: list[InvestigationStepRecord],
    ) -> None:
        self._session.execute(
            delete(InvestigationStep).where(
                InvestigationStep.investigation_id == investigation_id
            )
        )
        for step in steps:
            self._session.add(
                step_record_to_model(investigation_id, step)
            )
        self._flush()

    def list_steps(
        self,
        investigation_id: str,
    ) -> list[InvestigationStepRecord]:
        models = list(
            self._session.scalars(
                select(InvestigationStep)
                .where(InvestigationStep.investigation_id == investigation_id)
                .order_by(InvestigationStep.step_order.asc())
            )
        )
        return [step_model_to_record(model) for model in models]

    def save_conflicts(
        self,
        investigation_id: str,
        conflicts: list[ConflictRecord],
    ) -> None:
        self._session.execute(
            delete(Conflict).where(
                Conflict.investigation_id == investigation_id
            )
        )
        for conflict in conflicts:
            self._session.add(
                conflict_record_to_model(investigation_id, conflict)
            )
        self._flush()

    def list_conflicts(
        self,
        investigation_id: str,
    ) -> list[ConflictRecord]:
        models = list(
            self._session.scalars(
                select(Conflict).where(
                    Conflict.investigation_id == investigation_id
                )
            )
        )
        return [conflict_model_to_record(model) for model in models]

    def save_report(
        self,
        investigation_id: str,
        report: InvestigationReportRecord,
    ) -> None:
        self._session.execute(
            delete(InvestigationReport).where(
                InvestigationReport.investigation_id == investigation_id
            )
        )
        self._session.add(
            report_record_to_model(investigation_id, report)
        )
        self._flush()

    def get_report(
        self,
        investigation_id: str,
    ) -> InvestigationReportRecord | None:
        model = self._session.scalar(
            select(InvestigationReport).where(
                InvestigationReport.investigation_id == investigation_id
            )
        )
        return (
            report_model_to_record(model)
            if model is not None
            else None
        )

    def clear(self) -> int:
        result = self._session.execute(delete(Investigation))
        self._flush()
        return int(result.rowcount or 0)

    def _flush(self) -> None:
        self._session.flush()


class SqlAlchemyDocumentRepository(DocumentRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, stored: StoredDocument) -> None:
        model = stored_document_to_model(stored)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError as exc:
            self._session.rollback()
            raise DuplicateDocumentHashError(
                f"a document with hash {stored.uploaded.content_hash!r} "
                "already exists"
            ) from exc

    def get(self, document_id: str) -> StoredDocument | None:
        model = self._session.scalar(
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.pages))
        )
        return document_model_to_stored(model) if model is not None else None

    def find_by_hash(self, content_hash: str) -> StoredDocument | None:
        model = self._session.scalar(
            select(Document)
            .where(Document.content_hash == content_hash)
            .options(selectinload(Document.pages))
        )
        return document_model_to_stored(model) if model is not None else None

    def list(
        self,
        *,
        limit: int,
        offset: int,
        kind: str | None = None,
    ) -> list[StoredDocument]:
        query = (
            select(Document)
            .order_by(Document.received_at.desc(), Document.id.desc())
            .limit(limit)
            .offset(offset)
        )
        if kind is not None:
            query = query.where(Document.kind == kind)
        models = list(self._session.scalars(query))
        return [document_model_to_stored(model) for model in models]

    def count(self, *, kind: str | None = None) -> int:
        query = select(func.count()).select_from(Document)
        if kind is not None:
            query = query.where(Document.kind == kind)
        return int(self._session.scalar(query) or 0)

    def delete(self, document_id: str) -> bool:
        model = self._session.get(Document, document_id)
        if model is None:
            return False
        self._session.delete(model)
        self._flush()
        return True

    def clear(self) -> int:
        result = self._session.execute(delete(Document))
        self._flush()
        return int(result.rowcount or 0)

    def _flush(self) -> None:
        self._session.flush()


class SqlAlchemySourceRepository(SourceRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_many(
        self,
        investigation_id: str,
        sources: list[SourceRecord],
    ) -> None:
        self._session.execute(
            delete(Source).where(Source.investigation_id == investigation_id)
        )
        for source in sources:
            self._session.add(source_record_to_model(investigation_id, source))
        self._session.flush()

    def list_for_investigation(
        self,
        investigation_id: str,
    ) -> list[SourceRecord]:
        models = list(
            self._session.scalars(
                select(Source)
                .where(Source.investigation_id == investigation_id)
                .order_by(Source.id.asc())
            )
        )
        return [source_model_to_record(model) for model in models]

    def clear(self) -> int:
        result = self._session.execute(delete(Source))
        self._session.flush()
        return int(result.rowcount or 0)


class SqlAlchemyEvidenceRepository(EvidenceRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_items(
        self,
        investigation_id: str,
        items: list[EvidenceItemRecord],
    ) -> None:
        self._session.execute(
            delete(EvidenceItem).where(
                EvidenceItem.investigation_id == investigation_id
            )
        )
        for item in items:
            self._session.add(
                evidence_record_to_model(investigation_id, item)
            )
        self._session.flush()

    def list_for_investigation(
        self,
        investigation_id: str,
    ) -> list[EvidenceItemRecord]:
        models = list(
            self._session.scalars(
                select(EvidenceItem)
                .where(EvidenceItem.investigation_id == investigation_id)
                .order_by(EvidenceItem.id.asc())
            )
        )
        return [evidence_model_to_record(model) for model in models]

    def clear(self) -> int:
        result = self._session.execute(delete(EvidenceItem))
        self._session.flush()
        return int(result.rowcount or 0)


__all__ = [
    "SqlAlchemyDocumentRepository",
    "SqlAlchemyEvidenceRepository",
    "SqlAlchemyInvestigationRepository",
    "SqlAlchemySourceRepository",
    "SqlAlchemyUserRepository",
]
