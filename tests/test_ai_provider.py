import asyncio
from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.ai.factory import create_llm_provider
from app.ai.mock_provider import MockLLMProvider
from app.core.config import settings
from app.core.exceptions import ApplicationConfigurationError
from app.schemas.investigation import (
    AIInvestigationPlan,
    InvestigationDepth,
)


def test_mock_provider_output_validates() -> None:
    provider = MockLLMProvider()
    payload = asyncio.run(
        provider.generate_investigation_plan(
            "Research renewable energy storage",
            InvestigationDepth.STANDARD,
        )
    )
    plan = AIInvestigationPlan.model_validate(payload)

    assert plan.depth is InvestigationDepth.STANDARD
    assert len(plan.sub_questions) == 5
    assert plan.research_objective.objective
    assert plan.assumptions
    assert plan.expected_evidence_types
    assert plan.potential_biases
    assert provider.last_prompt is not None
    assert "Required JSON Schema" in provider.last_prompt


def test_mock_provider_depth_outputs() -> None:
    provider = MockLLMProvider()
    expected_counts = {
        InvestigationDepth.QUICK: 3,
        InvestigationDepth.STANDARD: 5,
        InvestigationDepth.DEEP: 8,
    }

    for depth, expected_count in expected_counts.items():
        payload = asyncio.run(
            provider.generate_investigation_plan(
                "Compare solar and wind power",
                depth,
            )
        )
        plan = AIInvestigationPlan.model_validate(payload)

        assert plan.depth is depth
        assert len(plan.sub_questions) == expected_count
        assert len(plan.research_angles) == expected_count


def test_provider_factory_returns_configured_mock() -> None:
    config = replace(
        settings,
        LLM_PROVIDER="mock",
        LLM_MODEL="test-mock-model",
    )

    provider = create_llm_provider(config)

    assert isinstance(provider, MockLLMProvider)
    assert provider.provider_name == "mock"
    assert provider.model_name == "test-mock-model"


def test_invalid_provider_configuration() -> None:
    config = replace(settings, LLM_PROVIDER="unsupported-provider")

    with pytest.raises(
        ApplicationConfigurationError,
        match="Unsupported LLM provider",
    ):
        create_llm_provider(config)


def test_ai_schema_rejects_incomplete_provider_output() -> None:
    with pytest.raises(ValidationError):
        AIInvestigationPlan.model_validate(
            {
                "query": "A valid investigation query",
                "depth": "standard",
            }
        )
