from fastapi import APIRouter

from app.schemas.common import ErrorResponse
from app.schemas.investigation import (
    InvestigationRequest,
    InvestigationResponse,
)
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
