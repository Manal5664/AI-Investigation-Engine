"""Version 1 route definitions for the investigation service."""

import asyncio

from fastapi import APIRouter

from app.agents.critic_agent import CriticAgent
from app.agents.evidence_agent import EvidenceAgent
from app.agents.orchestrator import InvestigationOrchestrator
from app.agents.research_agent import ResearchAgent
from app.ai.factory import create_llm_provider
from app.api.v1.documents_routes import router as documents_router
from app.api.v1.persistence_routes import router as persistence_router
from app.api.v1.research_routes import router as research_router
from app.api.v1.rag_routes import router as rag_router
from app.core.config import settings
from app.database.provider import get_persistence_provider
from app.evidence.factory import create_evidence_extractor
from app.graph.extraction.factory import create_graph_extraction_provider
from app.graph.factory import get_graph_store
from app.rag.embeddings.factory import create_embedding_provider
from app.rag.vectorstore.factory import get_vector_store
from app.research.search.factory import create_search_provider
from app.schemas.common import ErrorResponse
from app.schemas.agentic import (
    AgenticInvestigationRequest,
    AgenticInvestigationResult,
)
from app.schemas.investigation import (
    AIInvestigationResponse,
    InvestigationRequest,
    InvestigationResponse,
)
from app.schemas.research import (
    InvestigationResearchRequest,
    InvestigationResearchResponse,
)
from app.services.ai_investigation_service import AIInvestigationService
from app.services.graph_builder_service import GraphBuilderService
from app.services.graph_rag_service import GraphRAGService
from app.services.investigation_service import InvestigationPlanner
from app.services.investigation_persistence_service import (
    InvestigationPersistenceService,
)
from app.services.investigation_research_service import (
    InvestigationResearchService,
)
from app.services.rag_indexing_service import RAGIndexingService
from app.services.rag_retrieval_service import RAGRetrievalService

router = APIRouter(prefix="/api/v1", tags=["investigations"])
planner = InvestigationPlanner()


@router.post(
    "/investigations/plan",
    response_model=InvestigationResponse,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "The request failed validation.",
        },
        500: {
            "model": ErrorResponse,
            "description": "An application error occurred.",
        },
    },
)
def create_investigation_plan(
    request: InvestigationRequest,
) -> InvestigationResponse:
    plan = planner.plan(request)
    return InvestigationResponse(
        status="investigation_planned",
        plan=plan,
    )


@router.post(
    "/investigations/ai-plan",
    response_model=AIInvestigationResponse,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "The request failed validation.",
        },
        500: {
            "model": ErrorResponse,
            "description": "An application or configuration error occurred.",
        },
    },
)
async def create_ai_investigation_plan(
    request: InvestigationRequest,
) -> AIInvestigationResponse:
    provider = create_llm_provider()
    try:
        service = AIInvestigationService(
            provider=provider,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        )
        return await service.plan_investigation(request)
    finally:
        await provider.aclose()


@router.post(
    "/investigations/research",
    response_model=InvestigationResearchResponse,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "The bounded research request failed validation.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Provider configuration is invalid.",
        },
        502: {
            "model": ErrorResponse,
            "description": "A research or evidence provider failed.",
        },
    },
)
async def research_investigation(
    request: InvestigationResearchRequest,
) -> InvestigationResearchResponse:
    search_provider = create_search_provider()
    evidence_extractor = None
    try:
        evidence_extractor = create_evidence_extractor()
        service = InvestigationResearchService(
            search_provider=search_provider,
            evidence_extractor=evidence_extractor,
        )
        return await service.research(request)
    finally:
        if evidence_extractor is not None:
            await evidence_extractor.aclose()
        await search_provider.aclose()


@router.post(
    "/investigations/agentic",
    response_model=AgenticInvestigationResult,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "The bounded agentic request failed validation.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Provider configuration is invalid.",
        },
        502: {
            "model": ErrorResponse,
            "description": "An agent provider failed before partial output.",
        },
    },
)
async def run_agentic_investigation(
    request: AgenticInvestigationRequest,
) -> AgenticInvestigationResult:
    search_provider = create_search_provider()
    evidence_extractor = None
    embedding_provider = None
    graph_extraction_provider = None
    try:
        evidence_extractor = create_evidence_extractor()
        rag_indexing_service = None
        rag_retrieval_service = None
        if request.use_rag or request.use_graph_rag:
            embedding_provider = create_embedding_provider()
            vector_store = get_vector_store()
            rag_indexing_service = RAGIndexingService(
                embedding_provider,
                vector_store,
            )
            rag_retrieval_service = RAGRetrievalService(
                embedding_provider,
                vector_store,
            )
        graph_builder_service = None
        graph_rag_service = None
        if request.use_graph_rag:
            graph_extraction_provider = create_graph_extraction_provider()
            graph_store = get_graph_store()
            graph_builder_service = GraphBuilderService(
                graph_store,
                graph_extraction_provider,
            )
            graph_rag_service = GraphRAGService(
                rag_retrieval_service=rag_retrieval_service,
                graph_store=graph_store,
            )
        research_agent = ResearchAgent(search_provider)
        evidence_agent = EvidenceAgent(evidence_extractor)
        critic_agent = CriticAgent(
            research_agent=research_agent,
            evidence_agent=evidence_agent,
            rag_indexing_service=rag_indexing_service,
            rag_retrieval_service=rag_retrieval_service,
        )
        orchestrator = InvestigationOrchestrator(
            research_agent=research_agent,
            evidence_agent=evidence_agent,
            critic_agent=critic_agent,
            rag_indexing_service=rag_indexing_service,
            rag_retrieval_service=rag_retrieval_service,
            graph_builder_service=graph_builder_service,
            graph_rag_service=graph_rag_service,
        )
        result = await orchestrator.investigate(request)
        persistence_service = InvestigationPersistenceService(
            get_persistence_provider()
        )
        await asyncio.to_thread(persistence_service.save_result, result)
        return result
    finally:
        if graph_extraction_provider is not None:
            await graph_extraction_provider.aclose()
        if embedding_provider is not None:
            await embedding_provider.aclose()
        if evidence_extractor is not None:
            await evidence_extractor.aclose()
        await search_provider.aclose()


router.include_router(research_router)
router.include_router(rag_router)
router.include_router(documents_router)
router.include_router(persistence_router)
