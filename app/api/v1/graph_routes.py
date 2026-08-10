from fastapi import APIRouter

from app.core.config import settings
from app.graph.extraction.factory import create_graph_extraction_provider
from app.graph.factory import get_graph_store
from app.rag.embeddings.factory import create_embedding_provider
from app.rag.vectorstore.factory import get_vector_store
from app.schemas.common import ErrorResponse
from app.schemas.graph import (
    GraphBuildRequest,
    GraphBuildResult,
    GraphQueryRequest,
    GraphQueryResult,
    GraphRAGRequest,
    GraphRAGResult,
    GraphStats,
)
from app.services.graph_builder_service import GraphBuilderService
from app.services.graph_rag_service import GraphRAGService
from app.services.graph_retrieval_service import GraphRetrievalService
from app.services.rag_retrieval_service import RAGRetrievalService


router = APIRouter(tags=["graph"])


@router.post(
    "/graph/build",
    response_model=GraphBuildResult,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "The graph build request failed validation.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Graph provider configuration is invalid.",
        },
        502: {
            "model": ErrorResponse,
            "description": "The graph extraction provider failed.",
        },
    },
)
async def build_graph(request: GraphBuildRequest) -> GraphBuildResult:
    extraction_provider = create_graph_extraction_provider()
    try:
        service = GraphBuilderService(
            get_graph_store(),
            extraction_provider,
        )
        return await service.build(request)
    finally:
        await extraction_provider.aclose()


@router.post(
    "/graph/query",
    response_model=GraphQueryResult,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "The graph query request failed validation.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Graph provider configuration is invalid.",
        },
    },
)
async def query_graph(request: GraphQueryRequest) -> GraphQueryResult:
    service = GraphRetrievalService(get_graph_store())
    return await service.query(request)


@router.post(
    "/graph-rag/search",
    response_model=GraphRAGResult,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "The GraphRAG search request failed validation.",
        },
        500: {
            "model": ErrorResponse,
            "description": "GraphRAG provider configuration is invalid.",
        },
        502: {
            "model": ErrorResponse,
            "description": "The embedding provider failed.",
        },
    },
)
async def graph_rag_search(request: GraphRAGRequest) -> GraphRAGResult:
    embedding_provider = create_embedding_provider()
    try:
        rag_retrieval = RAGRetrievalService(
            embedding_provider,
            get_vector_store(),
        )
        service = GraphRAGService(
            rag_retrieval_service=rag_retrieval,
            graph_store=get_graph_store(),
        )
        return await service.search(request)
    finally:
        await embedding_provider.aclose()


@router.get(
    "/graph/stats",
    response_model=GraphStats,
)
async def graph_stats() -> GraphStats:
    stats = await get_graph_store().stats()
    return stats.model_copy(
        update={"store_type": settings.GRAPH_STORE_PROVIDER}
    )
