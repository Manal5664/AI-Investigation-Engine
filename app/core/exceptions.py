from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.common import ErrorDetail, ErrorResponse


class ApplicationError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "application_error",
        status_code: int = 500,
        details: list[ErrorDetail] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or []


async def application_error_handler(
    request: Request,
    exc: ApplicationError,
) -> JSONResponse:
    del request
    response = ErrorResponse(
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(),
    )


async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    del request
    details: list[ErrorDetail] = []
    for error in exc.errors():
        location = list(error["loc"])
        if location and location[0] in {"body", "query", "path"}:
            location = location[1:]
        details.append(
            ErrorDetail(
                field=".".join(str(part) for part in location) or "request",
                message=error["msg"],
                type=error["type"],
            )
        )

    response = ErrorResponse(
        code="validation_error",
        message="Request validation failed",
        details=details,
    )
    return JSONResponse(status_code=422, content=response.model_dump())
