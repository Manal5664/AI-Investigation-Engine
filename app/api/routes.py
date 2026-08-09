from fastapi import APIRouter

from app.api.v1.routes import router as v1_router
from app.core.config import settings
from app.schemas.common import HealthResponse, RootResponse

router = APIRouter()


@router.get("/", response_model=RootResponse)
def home() -> RootResponse:
    return RootResponse(
        message=f"{settings.APP_NAME} is running successfully"
    )


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        environment=settings.ENVIRONMENT,
    )


router.include_router(v1_router)
