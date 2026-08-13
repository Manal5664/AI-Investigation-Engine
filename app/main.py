import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import PROJECT_ROOT, settings, validate_production_configuration
from app.core.exceptions import (
    ApplicationError,
    application_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware

configure_logging()

logger = logging.getLogger("app.main")


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    del request
    content = {
        "code": "internal_error",
        "message": "An internal server error occurred.",
        "details": [],
    }
    if settings.DEBUG:
        content["details"].append(
            {
                "field": "exception",
                "message": f"{type(exc).__name__}: {exc}",
                "type": type(exc).__name__,
            }
        )
    return JSONResponse(status_code=500, content=content)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_production_configuration()
    logger.info(
        "application_started",
        extra={
            "extra_fields": {
                "environment": settings.ENVIRONMENT,
                "version": settings.APP_VERSION,
                "persistence_provider": settings.PERSISTENCE_PROVIDER,
            }
        },
    )
    yield
    logger.info("application_stopped")


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "An investigation planning, grounded web research, and evidence "
        "service with deterministic and provider-backed flows, plus a "
        "browser UI for case management."
    ),
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

if settings.CORS_ALLOWED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.CORS_ALLOWED_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
app.add_middleware(RequestContextMiddleware)

app.add_exception_handler(ApplicationError, application_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, internal_error_handler)
app.mount(
    "/static",
    StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")),
    name="static",
)
app.include_router(router)
