from fastapi import APIRouter

from app.evidence.mock_extractor import MockEvidenceExtractor
from app.core.config import settings
from app.research.search.factory import create_search_provider
from app.schemas.common import ErrorResponse
from app.schemas.evidence import EvidenceSummary
from app.schemas.investigation import InvestigationRequest
from app.schemas.research import (
    ResearchRequest,
    ResearchResult,
    WebResearchRequest,
    WebResearchResult,
)
from app.services.evidence_summary_service import EvidenceSummaryService
from app.services.investigation_service import InvestigationPlanner
from app.services.research_service import ResearchService
from app.services.web_research_service import WebResearchService

router = APIRouter(tags=["research", "evidence"])
planner = InvestigationPlanner()
evidence_summary_service = EvidenceSummaryService()


@router.post(
    "/research/mock",
    response_model=ResearchResult,
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
async def run_mock_research(request: ResearchRequest) -> ResearchResult:
    investigation_plan = planner.plan(
        InvestigationRequest(
            query=request.investigation_query,
            depth=request.depth,
        )
    )
    service = ResearchService(
        search_provider=create_search_provider("mock"),
        evidence_extractor=MockEvidenceExtractor(),
    )
    return await service.research(
        investigation_plan,
        sub_question=request.sub_question,
        max_results=request.max_results,
    )


@router.post(
    "/research/web",
    response_model=WebResearchResult,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "The request failed validation.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Search configuration is invalid.",
        },
        502: {
            "model": ErrorResponse,
            "description": "The grounded search provider failed.",
        },
    },
)
async def run_web_research(
    request: WebResearchRequest,
) -> WebResearchResult:
    provider = create_search_provider("gemini_grounded")
    configured_max_results = min(
        request.max_results,
        settings.SEARCH_MAX_RESULTS,
    )
    try:
        service = WebResearchService(provider)
        result = await service.research(
            request.query,
            max_results=configured_max_results,
        )
        if configured_max_results < request.max_results:
            result = result.model_copy(
                update={
                    "warnings": [
                        *result.warnings,
                        (
                            "Requested max_results was limited by "
                            f"SEARCH_MAX_RESULTS={settings.SEARCH_MAX_RESULTS}."
                        ),
                    ]
                }
            )
        return result
    finally:
        await provider.aclose()


@router.post(
    "/evidence/summary",
    response_model=EvidenceSummary,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "The research result failed validation.",
        },
    },
)
def summarize_evidence(
    research_result: ResearchResult,
) -> EvidenceSummary:
    return evidence_summary_service.summarize(research_result)
