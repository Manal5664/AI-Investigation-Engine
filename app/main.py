from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import PROJECT_ROOT, settings
from app.core.exceptions import (
    ApplicationError,
    application_error_handler,
    validation_error_handler,
)


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    del request, exc
    return JSONResponse(
        status_code=500,
        content={
            "code": "internal_error",
            "message": "An internal server error occurred.",
            "details": [],
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    yield


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

app.add_exception_handler(ApplicationError, application_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, internal_error_handler)
app.mount(
    "/static",
    StaticFiles(directory=str(PROJECT_ROOT / "app" / "static")),
    name="static",
)
app.include_router(router)
