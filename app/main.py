from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.routes import router
from app.core.config import settings
from app.core.exceptions import (
    ApplicationError,
    application_error_handler,
    validation_error_handler,
)

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "A deterministic investigation planning service designed for future "
        "LLM integration."
    ),
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
)

app.add_exception_handler(ApplicationError, application_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.include_router(router)
