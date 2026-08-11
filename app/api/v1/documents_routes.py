"""HTTP endpoints for the document management subsystem."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.core.config import settings
from app.database.persistence_gateway import DocumentPersistenceGateway
from app.database.provider import get_persistence_provider
from app.documents.base import DocumentStore
from app.documents.extractors.factory import ExtractorFactory
from app.documents.factory import get_document_store
from app.documents.reporting import DocumentReportGeneratorError
from app.documents.reporting_factory import create_document_report_generator
from app.documents.vision.factory import create_vision_provider
from app.graph.factory import get_graph_store
from app.rag.embeddings.factory import create_embedding_provider
from app.rag.vectorstore.factory import get_vector_store
from app.schemas.common import ErrorResponse
from app.schemas.documents import (
    DeleteDocumentsRequest,
    DeleteDocumentsResponse,
    DocumentGraphMappingRequest,
    DocumentGraphMappingResponse,
    DocumentIndexResponse,
    DocumentInvestigationReport,
    DocumentInvestigationRequest,
    DocumentStoreStatsResponse,
    GetDocumentResponse,
    ListDocumentsRequest,
    ListDocumentsResponse,
    StoredDocumentSummary,
    UploadDocumentsResponse,
)
from app.services.document_graph_service import DocumentGraphService
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.document_investigation_service import (
    DocumentInvestigationService,
)
from app.services.document_rag_service import DocumentRAGService

router = APIRouter(prefix="/documents", tags=["documents"])


def _document_store() -> DocumentStore:
    return get_document_store()


def _extractor_factory() -> ExtractorFactory:
    return ExtractorFactory(create_vision_provider(settings))


def _ingestion_service(
    store: DocumentStore = Depends(_document_store),
) -> DocumentIngestionService:
    return DocumentIngestionService(
        store=store,
        extractor_factory=_extractor_factory(),
        max_bytes=settings.DOCUMENT_MAX_UPLOAD_BYTES,
        max_pages=settings.DOCUMENT_MAX_PAGES,
        max_per_request=settings.DOCUMENT_MAX_PER_REQUEST,
        document_repository=DocumentPersistenceGateway(
            get_persistence_provider()
        ),
    )


def _rag_service(
    store: DocumentStore = Depends(_document_store),
) -> DocumentRAGService:
    return DocumentRAGService(
        document_store=store,
        embedding_provider=create_embedding_provider(),
        vector_store=get_vector_store(),
        chunk_size=settings.RAG_CHUNK_SIZE,
        overlap=settings.RAG_CHUNK_OVERLAP,
        top_k=10,
    )


def _investigation_service(
    store: DocumentStore = Depends(_document_store),
) -> DocumentInvestigationService:
    return DocumentInvestigationService(
        document_store=store,
        generator=create_document_report_generator(),
        rag_service=_rag_service(store),
        graph_store=get_graph_store(),
    )


_executor = ThreadPoolExecutor(max_workers=4)


async def _read_upload_bytes(files: list[UploadFile]) -> list[tuple[str, str, bytes]]:
    def _read_one(file: UploadFile) -> tuple[str, str, bytes]:
        content = file.file.read()
        return (file.filename or "untitled", file.content_type or "", content)

    loop = asyncio.get_running_loop()
    return await asyncio.gather(
        *(loop.run_in_executor(_executor, _read_one, f) for f in files)
    )


@router.post(
    "/upload",
    response_model=UploadDocumentsResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Upload validation failed."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def upload_documents(
    files: list[UploadFile] = File(...),
    service: DocumentIngestionService = Depends(_ingestion_service),
) -> UploadDocumentsResponse:
    if not files:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="no files were uploaded")
    uploaded = await _read_upload_bytes(files)
    results = await service.ingest(uploaded)
    return UploadDocumentsResponse(
        status="completed",
        documents=results,
    )


@router.get(
    "/store",
    response_model=DocumentStoreStatsResponse,
    responses={
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def document_store_stats(
    store: DocumentStore = Depends(_document_store),
) -> DocumentStoreStatsResponse:
    return DocumentStoreStatsResponse(
        status="completed",
        stats=await store.stats(),
    )


@router.get(
    "/list",
    response_model=ListDocumentsResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Request validation failed."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def list_documents(
    kind: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    store: DocumentStore = Depends(_document_store),
) -> ListDocumentsResponse:
    request = ListDocumentsRequest(kind=kind, limit=limit, offset=offset)
    stored = await store.list_all(
        kind=request.kind.value if request.kind else None,
        limit=request.limit,
        offset=request.offset,
    )
    documents = [
        StoredDocumentSummary(
            uploaded=item.uploaded,
            page_count=item.extracted.page_count,
            character_count=item.extracted.character_count,
            extraction_method=item.extracted.extraction_method,
            requires_vision_pages=sum(
                1 for page in item.extracted.pages if page.requires_vision
            ),
        )
        for item in stored
    ]
    all_documents = await store.list_all(limit=1000)
    total = len(all_documents)
    return ListDocumentsResponse(
        status="completed",
        documents=documents,
        total=total,
    )


@router.get(
    "/{document_id}",
    response_model=GetDocumentResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Document not found."},
        422: {"model": ErrorResponse, "description": "Invalid document ID."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def get_document(
    document_id: str,
    store: DocumentStore = Depends(_document_store),
) -> GetDocumentResponse:
    from fastapi import HTTPException

    stored = await store.get(document_id)
    if stored is None:
        stored = await DocumentPersistenceGateway(
            get_persistence_provider()
        ).get(document_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="document not found")
    return GetDocumentResponse(
        status="completed",
        document=stored.extracted,
    )


@router.post(
    "/delete",
    response_model=DeleteDocumentsResponse,
    responses={
        404: {"model": ErrorResponse, "description": "A document was not found."},
        422: {"model": ErrorResponse, "description": "Request validation failed."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def delete_documents(
    request: DeleteDocumentsRequest,
    store: DocumentStore = Depends(_document_store),
) -> DeleteDocumentsResponse:
    deleted = 0
    for document_id in request.document_ids:
        if await store.delete(document_id):
            deleted += 1
    return DeleteDocumentsResponse(status="completed", deleted_count=deleted)


@router.post(
    "/{document_id}/graph",
    response_model=DocumentGraphMappingResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Document not found."},
        422: {"model": ErrorResponse, "description": "Invalid document ID."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def index_document_graph(
    request: DocumentGraphMappingRequest,
    store: DocumentStore = Depends(_document_store),
) -> DocumentGraphMappingResponse:
    from fastapi import HTTPException

    if await store.get(request.document_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    service = DocumentGraphService(
        graph_store=get_graph_store(),
        document_store=store,
    )
    nodes, edges = await service.index_document(request.document_id)
    return DocumentGraphMappingResponse(
        status="completed",
        node_count=len(nodes),
        edge_count=len(edges),
        nodes=nodes,
        edges=edges,
    )


@router.post(
    "/{document_id}/index",
    response_model=DocumentIndexResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Document not found."},
        422: {"model": ErrorResponse, "description": "Invalid document ID."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def index_document_for_rag(
    document_id: str,
    store: DocumentStore = Depends(_document_store),
) -> DocumentIndexResponse:
    from fastapi import HTTPException

    if await store.get(document_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    service = _rag_service(store)
    result = await service.index_document(document_id)
    if result is None:
        return DocumentIndexResponse(status="skipped", document_id=document_id)
    return DocumentIndexResponse(
        status="completed",
        document_id=result.document_id,
        pages_indexed=result.pages_indexed,
        chunks_created=result.chunks_created,
        duplicates_skipped=result.duplicates_skipped,
        failures=result.failures,
    )


@router.post(
    "/investigations",
    response_model=DocumentInvestigationReport,
    responses={
        422: {"model": ErrorResponse, "description": "Request validation failed."},
        502: {"model": ErrorResponse, "description": "Report generation failed."},
        500: {"model": ErrorResponse, "description": "An application error occurred."},
    },
)
async def investigate_documents(
    request: DocumentInvestigationRequest,
    service: DocumentInvestigationService = Depends(_investigation_service),
) -> DocumentInvestigationReport:
    try:
        return await service.investigate(request)
    except DocumentReportGeneratorError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail=str(exc)) from exc


__all__ = ["router"]
