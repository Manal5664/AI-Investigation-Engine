import asyncio
from typing import Any

from app.ai.base import LLMProvider, LLMProviderError
from app.ai.mock_provider import MockLLMProvider
from app.schemas.investigation import (
    AIInvestigationPlan,
    InvestigationDepth,
    InvestigationPlan,
    InvestigationRequest,
)
from app.services.ai_investigation_service import AIInvestigationService


class FailingProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "failing"

    @property
    def model_name(self) -> str:
        return "failing-model"

    async def generate_investigation_plan(
        self,
        query: str,
        depth: InvestigationDepth,
    ) -> dict[str, Any]:
        del query, depth
        raise LLMProviderError("Simulated provider failure")


class InvalidOutputProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "invalid-output"

    @property
    def model_name(self) -> str:
        return "invalid-output-model"

    async def generate_investigation_plan(
        self,
        query: str,
        depth: InvestigationDepth,
    ) -> dict[str, Any]:
        return {
            "query": query,
            "depth": depth.value,
            "invalid": True,
        }


def test_ai_planning_service_returns_validated_plan() -> None:
    service = AIInvestigationService(MockLLMProvider())
    request = InvestigationRequest(
        query="Research renewable energy storage",
        depth=InvestigationDepth.DEEP,
    )

    response = asyncio.run(service.plan_investigation(request))

    assert isinstance(response.plan, AIInvestigationPlan)
    assert response.plan.depth is InvestigationDepth.DEEP
    assert len(response.plan.sub_questions) == 8


def test_deterministic_fallback_on_provider_error() -> None:
    service = AIInvestigationService(FailingProvider())
    request = InvestigationRequest(
        query="Investigate unusual patterns in these records",
        depth=InvestigationDepth.QUICK,
    )

    response = asyncio.run(service.plan_investigation(request))

    assert type(response.plan) is InvestigationPlan
    assert len(response.plan.sub_questions) == 3


def test_deterministic_fallback_on_schema_validation_error() -> None:
    service = AIInvestigationService(InvalidOutputProvider())
    request = InvestigationRequest(
        query="Investigate unusual patterns in these records"
    )

    response = asyncio.run(service.plan_investigation(request))

    assert type(response.plan) is InvestigationPlan
    assert len(response.plan.sub_questions) == 5
