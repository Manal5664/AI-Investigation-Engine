import asyncio

from pydantic import ValidationError

from app.ai.base import LLMProvider, LLMProviderError
from app.core.config import settings
from app.schemas.investigation import (
    AIInvestigationPlan,
    InvestigationRequest,
    InvestigationResponse,
)
from app.services.investigation_service import InvestigationPlanner


class AIInvestigationService:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        fallback_planner: InvestigationPlanner | None = None,
        timeout_seconds: int = settings.LLM_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self._provider = provider
        self._fallback_planner = fallback_planner or InvestigationPlanner()
        self._timeout_seconds = timeout_seconds

    async def plan_investigation(
        self,
        request: InvestigationRequest,
    ) -> InvestigationResponse:
        try:
            provider_payload = await asyncio.wait_for(
                self._provider.generate_investigation_plan(
                    request.query,
                    request.depth,
                ),
                timeout=self._timeout_seconds,
            )
            plan = AIInvestigationPlan.model_validate(provider_payload)
        except (LLMProviderError, TimeoutError, ValidationError):
            plan = self._fallback_planner.plan(request)

        return InvestigationResponse(
            status="investigation_planned",
            plan=plan,
        )
