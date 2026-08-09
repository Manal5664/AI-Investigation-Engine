from fastapi import APIRouter

from app.evidence.mock_extractor import MockEvidenceExtractor
from app.research.search.factory import create_search_provider
from app.schemas.common import ErrorResponse
from app.schemas.evidence import EvidenceSummary
from app.schemas.investigation import InvestigationRequest
from app.schemas.research import ResearchRequest, ResearchResult
from app.services.evidence_summary_service import EvidenceSummaryService
from app.services.investigation_service import InvestigationPlanner
from app.services.research_service import ResearchService

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
