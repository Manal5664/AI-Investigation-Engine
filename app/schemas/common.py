from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RootResponse(StrictResponseModel):
    message: str


class HealthResponse(StrictResponseModel):
    status: Literal["healthy"]
    environment: str


class LivenessResponse(StrictResponseModel):
    status: Literal["alive"]


class ReadinessCheck(StrictResponseModel):
    name: str
    ok: bool
    detail: str | None = None


class ReadinessResponse(StrictResponseModel):
    status: Literal["ready", "not_ready"]
    persistence_provider: str
    checks: list[ReadinessCheck]


class ErrorDetail(StrictResponseModel):
    field: str
    message: str
    type: str


class ErrorResponse(StrictResponseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
