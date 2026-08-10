from fastapi import APIRouter

from app.core.config import settings
from app.rag.embeddings.factory import create_embedding_provider
from app.rag.vectorstore.factory import get_vector_store
from app.schemas.common import ErrorResponse
from app.schemas.rag import (
    IndexRequest,
    IndexResult,
    RetrievalRequest,
    RetrievalResult,
    VectorStoreStats,
)
from app.services.rag_indexing_service import RAGIndexingService
from app.services.rag_retrieval_service import RAGRetrievalService


router = APIRouter(prefix="/rag", tags=["rag"])


@router.post(
    "/index",
    response_model=IndexResult,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "The indexing request failed validation.",
        },
        500: {
            "model": ErrorResponse,
            "description": "RAG provider configuration is invalid.",
        },
        502: {
            "model": ErrorResponse,
            "description": "The embedding provider failed.",
        },
    },
)
async def index_sources(request: IndexRequest) -> IndexResult:
    provider = create_embedding_provider()
    try:
        service = RAGIndexingService(
            provider,
            get_vector_store(),
        )
        return await service.index(request)
    finally:
        await provider.aclose()


@router.post(
    "/search",
    response_model=list[RetrievalResult],
    responses={
        422: {
            "model": ErrorResponse,
            "description": "The retrieval request failed validation.",
        },
        500: {
            "model": ErrorResponse,
            "description": "RAG provider configuration is invalid.",
        },
        502: {
            "model": ErrorResponse,
            "description": "The embedding provider failed.",
        },
    },
)
async def search_chunks(
    request: RetrievalRequest,
) -> list[RetrievalResult]:
    provider = create_embedding_provider()
    try:
        service = RAGRetrievalService(
            provider,
            get_vector_store(),
        )
        return await service.retrieve(request)
    finally:
        await provider.aclose()


@router.get("/stats", response_model=VectorStoreStats)
async def rag_stats() -> VectorStoreStats:
    stats = await get_vector_store().stats()
    return stats.model_copy(
        update={
            "embedding_provider": settings.EMBEDDING_PROVIDER,
            "embedding_model": settings.EMBEDDING_MODEL,
        }
    )
