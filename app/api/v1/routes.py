from fastapi import APIRouter

from app.ai.factory import create_llm_provider
from app.api.v1.research_routes import router as research_router
from app.core.config import settings
from app.schemas.common import ErrorResponse
from app.schemas.investigation import (
    InvestigationRequest,
    InvestigationResponse,
)
from app.services.ai_investigation_service import AIInvestigationService
from app.services.investigation_service import InvestigationPlanner

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
    response_model=InvestigationResponse,
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
) -> InvestigationResponse:
    service = AIInvestigationService(
        provider=create_llm_provider(),
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )
    return await service.plan_investigation(request)


router.include_router(research_router)
