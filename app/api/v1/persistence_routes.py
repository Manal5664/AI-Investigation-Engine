"""HTTP endpoints for persisted users, investigations, and documents."""

import asyncio
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query

from app.database.persistence_gateway import DocumentPersistenceGateway
from app.database.provider import PersistenceProvider, get_persistence_provider
from app.database.repositories import DuplicateResourceError
from app.documents.factory import get_document_store
from app.documents.models import StoredDocument
from app.schemas.common import ErrorResponse
from app.schemas.persistence import (
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentRecord,
    InvestigationDeleteResponse,
    InvestigationDetailResponse,
    InvestigationListResponse,
    InvestigationSummaryResponse,
    UserCreate,
    UserRecord,
    UserResponse,
)

router = APIRouter(tags=["persistence"])


def _provider() -> PersistenceProvider:
    return get_persistence_provider()


async def _run(fn):
    """Run a repository callback inside a unit of work.

    SQLAlchemy calls are marshalled onto a worker thread (the sync session
    must stay on one thread for its whole life); in-memory calls run inline.
    """
    provider = get_persistence_provider()
    if provider.requires_transaction:
        def run() -> object:
            uow = provider.unit_of_work()
            try:
                result = fn(uow)
                uow.commit()
                return result
            except Exception:
                uow.rollback()
                raise
            finally:
                uow.close()

        return await asyncio.to_thread(run)
    uow = provider.unit_of_work()
    try:
        return fn(uow)
    finally:
        uow.close()


def _document_record(stored: StoredDocument) -> DocumentRecord:
    uploaded = stored.uploaded
    extracted = stored.extracted
    return DocumentRecord(
        document_id=uploaded.document_id,
        filename=uploaded.filename,
        mime_type=uploaded.mime_type,
        file_size_bytes=uploaded.file_size_bytes,
        content_hash=uploaded.content_hash,
        kind=uploaded.kind.value,
        extension=uploaded.extension,
        extraction_method=extracted.extraction_method,
        page_count=extracted.page_count,
        character_count=extracted.character_count,
        requires_vision_pages=sum(
            1 for page in extracted.pages if page.requires_vision
        ),
        received_at=uploaded.received_at,
        extracted_at=extracted.extracted_at,
        warnings=list(extracted.warnings),
    )


def _user_listing(uow, *, limit: int, offset: int) -> tuple[list[UserRecord], int]:
    return (
        uow.repositories.users.list(limit=limit, offset=offset),
        uow.repositories.users.count(),
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@router.post(
    "/users",
    response_model=UserResponse,
    responses={
        409: {"model": ErrorResponse, "description": "Email already exists."},
        422: {"model": ErrorResponse, "description": "Request validation failed."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def create_user(request: UserCreate) -> UserResponse:
    def work(uow) -> UserRecord:
        now = datetime.now(UTC)
        record = UserRecord(
            id=f"user-{secrets.token_hex(6)}",
            email=request.email,
            display_name=request.display_name,
            created_at=now,
            updated_at=now,
            is_active=True,
        )
        return uow.repositories.users.create(record)

    try:
        user = await _run(work)
    except DuplicateResourceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return UserResponse(status="completed", user=user)


@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    responses={
        404: {"model": ErrorResponse, "description": "User not found."},
        422: {"model": ErrorResponse, "description": "Invalid user ID."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def get_user(user_id: str) -> UserResponse:
    user = await _run(
        lambda uow: uow.repositories.users.get(user_id)
    )
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    return UserResponse(status="completed", user=user)


# ---------------------------------------------------------------------------
# Investigations
# ---------------------------------------------------------------------------


@router.get(
    "/investigations",
    response_model=InvestigationListResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Request validation failed."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def list_investigations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> InvestigationListResponse:
    def work(uow):
        records = uow.repositories.investigations.list(
            limit=limit,
            offset=offset,
        )
        total = uow.repositories.investigations.count()
        return records, total

    records, total = await _run(work)
    summaries = [
        InvestigationSummaryResponse(
            id=record.id,
            query=record.query,
            depth=record.depth,
            category=record.category,
            status=record.status,
            provider_used=record.provider_used,
            model_used=record.model_used,
            created_at=record.created_at,
            completed_at=record.completed_at,
            confidence=record.confidence,
            total_source_count=record.total_source_count,
            total_evidence_count=record.total_evidence_count,
        )
        for record in records
    ]
    return InvestigationListResponse(
        status="completed",
        investigations=summaries,
        total=total,
    )


@router.get(
    "/investigations/{investigation_id}",
    response_model=InvestigationDetailResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Investigation not found."},
        422: {"model": ErrorResponse, "description": "Invalid investigation ID."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def get_investigation(investigation_id: str) -> InvestigationDetailResponse:
    detail = await _run(
        lambda uow: uow.repositories.investigations.get_detail(
            investigation_id
        )
    )
    if detail is None:
        raise HTTPException(
            status_code=404, detail="investigation not found"
        )
    return InvestigationDetailResponse(
        status="completed",
        investigation=detail.investigation,
        steps=detail.steps,
        sources=detail.sources,
        evidence_items=detail.evidence_items,
        conflicts=detail.conflicts,
        report=detail.report,
    )


@router.delete(
    "/investigations/{investigation_id}",
    response_model=InvestigationDeleteResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Investigation not found."},
        422: {"model": ErrorResponse, "description": "Invalid investigation ID."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def delete_investigation(investigation_id: str) -> InvestigationDeleteResponse:
    deleted = await _run(
        lambda uow: uow.repositories.investigations.delete(investigation_id)
    )
    if not deleted:
        raise HTTPException(
            status_code=404, detail="investigation not found"
        )
    return InvestigationDeleteResponse(
        status="completed",
        investigation_id=investigation_id,
        deleted=True,
    )


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Request validation failed."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def list_documents(
    kind: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    def work(uow):
        stored = uow.repositories.documents.list(
            limit=limit,
            offset=offset,
            kind=kind,
        )
        total = uow.repositories.documents.count(kind=kind)
        return stored, total

    stored, total = await _run(work)
    return DocumentListResponse(
        status="completed",
        documents=[_document_record(item) for item in stored],
        total=total,
    )


@router.delete(
    "/documents/{document_id}",
    response_model=DocumentDeleteResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Document not found."},
        422: {"model": ErrorResponse, "description": "Invalid document ID."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def delete_document(document_id: str) -> DocumentDeleteResponse:
    gateway = DocumentPersistenceGateway(get_persistence_provider())
    deleted_repository = await gateway.delete(document_id)
    deleted_store = await get_document_store().delete(document_id)
    if not deleted_repository and not deleted_store:
        raise HTTPException(status_code=404, detail="document not found")
    return DocumentDeleteResponse(
        status="completed",
        document_id=document_id,
        deleted=True,
    )


__all__ = ["router"]
