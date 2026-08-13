import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.ui_routes import router as ui_router
from app.api.v1.routes import router as v1_router
from app.core.config import settings
from app.database.provider import get_persistence_provider
from app.database.session import check_database_connection
from app.schemas.common import (
    HealthResponse,
    LivenessResponse,
    ReadinessCheck,
    ReadinessResponse,
    RootResponse,
)

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


@router.get("/health/live", response_model=LivenessResponse)
def health_live() -> LivenessResponse:
    return LivenessResponse(status="alive")


@router.get("/health/ready", response_model=ReadinessResponse)
async def health_ready() -> ReadinessResponse:
    checks: list[ReadinessCheck] = []
    provider_name = "unknown"
    try:
        provider = get_persistence_provider()
        provider_name = provider.name
        checks.append(
            ReadinessCheck(
                name="persistence_provider",
                ok=True,
                detail=provider.name,
            )
        )
    except Exception as exc:
        checks.append(
            ReadinessCheck(
                name="persistence_provider",
                ok=False,
                detail=type(exc).__name__,
            )
        )
        return _readiness_response(provider_name, checks, ready=False)

    if provider.requires_transaction:
        database_ok = await asyncio.to_thread(check_database_connection)
        checks.append(
            ReadinessCheck(
                name="database",
                ok=database_ok,
                detail="SELECT 1" if database_ok else "database unreachable",
            )
        )
        return _readiness_response(
            provider_name,
            checks,
            ready=database_ok,
        )

    return _readiness_response(provider_name, checks, ready=True)


def _readiness_response(
    provider_name: str,
    checks: list[ReadinessCheck],
    *,
    ready: bool,
) -> JSONResponse:
    payload = ReadinessResponse(
        status="ready" if ready else "not_ready",
        persistence_provider=provider_name,
        checks=checks,
    )
    return JSONResponse(
        status_code=200 if ready else 503,
        content=payload.model_dump(),
    )


router.include_router(v1_router)
router.include_router(ui_router)
