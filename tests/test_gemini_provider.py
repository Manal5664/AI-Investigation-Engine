import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from google.genai import errors

from app.ai.base import LLMProviderError
from app.ai.factory import create_llm_provider
from app.ai.gemini_provider import GeminiLLMProvider
from app.ai.mock_provider import MockLLMProvider
from app.core.config import settings
from app.core.exceptions import ApplicationConfigurationError
from app.schemas.investigation import (
    AIInvestigationPlan,
    InvestigationDepth,
    InvestigationRequest,
)
from app.services.ai_investigation_service import AIInvestigationService


def _fake_client(
    *,
    response_text: str | None = None,
    side_effect: BaseException | None = None,
) -> tuple[Any, AsyncMock]:
    generate_content = AsyncMock(
        return_value=SimpleNamespace(text=response_text),
        side_effect=side_effect,
    )
    client = SimpleNamespace(
        aio=SimpleNamespace(
            models=SimpleNamespace(generate_content=generate_content)
        )
    )
    return client, generate_content


def _valid_plan_json(
    query: str = "Research renewable energy storage",
    depth: InvestigationDepth = InvestigationDepth.STANDARD,
) -> str:
    payload = asyncio.run(
        MockLLMProvider().generate_investigation_plan(query, depth)
    )
    return json.dumps(payload)


def test_gemini_provider_success_uses_structured_output() -> None:
    client, generate_content = _fake_client(
        response_text=_valid_plan_json()
    )
    provider = GeminiLLMProvider(
        model_name="configured-gemini-model",
        api_key="test-api-key",
        client=client,
    )

    payload = asyncio.run(
        provider.generate_investigation_plan(
            "Research renewable energy storage",
            InvestigationDepth.STANDARD,
        )
    )
    plan = AIInvestigationPlan.model_validate(payload)

    assert plan.depth is InvestigationDepth.STANDARD
    assert provider.provider_name == "gemini"
    assert provider.model_name == "configured-gemini-model"

    call = generate_content.await_args
    assert call is not None
    assert call.kwargs["model"] == "configured-gemini-model"
    prompt = call.kwargs["contents"]
    assert "research objective" in prompt
    assert "assumptions requiring validation" in prompt
    assert "prioritized sub-questions" in prompt
    assert "expected evidence" in prompt
    assert "potential biases" in prompt
    assert "Do not make unsupported conclusions" in prompt
    assert "Return only valid JSON" in prompt
    assert "Required JSON Schema" not in prompt

    config = call.kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == (
        AIInvestigationPlan.model_json_schema()
    )


def test_gemini_provider_requires_api_key() -> None:
    with pytest.raises(
        ApplicationConfigurationError,
        match="GEMINI_API_KEY is required",
    ):
        GeminiLLMProvider(
            model_name="configured-gemini-model",
            api_key="  ",
        )


def test_gemini_provider_rejects_malformed_json() -> None:
    client, _ = _fake_client(response_text="not valid json")
    provider = GeminiLLMProvider(
        model_name="configured-gemini-model",
        api_key="test-api-key",
        client=client,
    )

    with pytest.raises(LLMProviderError, match="malformed JSON"):
        asyncio.run(
            provider.generate_investigation_plan(
                "Research renewable energy storage",
                InvestigationDepth.STANDARD,
            )
        )


def test_gemini_provider_rejects_schema_invalid_json() -> None:
    client, _ = _fake_client(
        response_text=json.dumps(
            {
                "query": "Research renewable energy storage",
                "depth": "standard",
            }
        )
    )
    provider = GeminiLLMProvider(
        model_name="configured-gemini-model",
        api_key="test-api-key",
        client=client,
    )

    with pytest.raises(LLMProviderError, match="schema validation"):
        asyncio.run(
            provider.generate_investigation_plan(
                "Research renewable energy storage",
                InvestigationDepth.STANDARD,
            )
        )


def test_gemini_provider_wraps_provider_error() -> None:
    client, _ = _fake_client(side_effect=RuntimeError("provider unavailable"))
    provider = GeminiLLMProvider(
        model_name="configured-gemini-model",
        api_key="test-api-key",
        client=client,
    )

    with pytest.raises(LLMProviderError, match="request failed"):
        asyncio.run(
            provider.generate_investigation_plan(
                "Research renewable energy storage",
                InvestigationDepth.STANDARD,
            )
        )


def test_gemini_provider_exposes_safe_client_error_details() -> None:
    provider_error = errors.ClientError(
        400,
        {
            "error": {
                "message": "API key test-api-key is invalid.",
                "status": "INVALID_ARGUMENT",
            }
        },
    )
    client, _ = _fake_client(side_effect=provider_error)
    provider = GeminiLLMProvider(
        model_name="configured-gemini-model",
        api_key="test-api-key",
        client=client,
    )

    with pytest.raises(LLMProviderError) as captured_error:
        asyncio.run(
            provider.generate_investigation_plan(
                "Research renewable energy storage",
                InvestigationDepth.STANDARD,
            )
        )

    message = str(captured_error.value)
    assert "code=400" in message
    assert "status=INVALID_ARGUMENT" in message
    assert "[redacted]" in message
    assert "test-api-key" not in message


def test_gemini_provider_times_out() -> None:
    client, _ = _fake_client(side_effect=TimeoutError())
    provider = GeminiLLMProvider(
        model_name="configured-gemini-model",
        api_key="test-api-key",
        client=client,
    )

    with pytest.raises(LLMProviderError, match="timed out"):
        asyncio.run(
            provider.generate_investigation_plan(
                "Research renewable energy storage",
                InvestigationDepth.STANDARD,
            )
        )


def test_provider_factory_selects_gemini() -> None:
    config = replace(
        settings,
        LLM_PROVIDER="gemini",
        LLM_MODEL="configured-gemini-model",
        LLM_TIMEOUT_SECONDS=15,
        GEMINI_API_KEY="test-api-key",
    )
    sentinel_provider = object()

    with patch(
        "app.ai.factory.GeminiLLMProvider",
        return_value=sentinel_provider,
    ) as provider_class:
        provider = create_llm_provider(config)

    assert provider is sentinel_provider
    provider_class.assert_called_once_with(
        model_name="configured-gemini-model",
        api_key="test-api-key",
        timeout_seconds=15,
    )


def test_provider_factory_rejects_gemini_without_api_key() -> None:
    config = replace(
        settings,
        LLM_PROVIDER="gemini",
        LLM_MODEL="configured-gemini-model",
        GEMINI_API_KEY=None,
    )

    with pytest.raises(
        ApplicationConfigurationError,
        match="GEMINI_API_KEY is required",
    ):
        create_llm_provider(config)


def test_gemini_service_response_contains_provider_metadata() -> None:
    client, _ = _fake_client(response_text=_valid_plan_json())
    provider = GeminiLLMProvider(
        model_name="configured-gemini-model",
        api_key="test-api-key",
        client=client,
    )
    service = AIInvestigationService(provider)

    response = asyncio.run(
        service.plan_investigation(
            InvestigationRequest(
                query="Research renewable energy storage",
                depth=InvestigationDepth.STANDARD,
            )
        )
    )

    assert response.provider_used == "gemini"
    assert response.model_used == "configured-gemini-model"
    assert response.fallback_used is False
    assert response.provider_error is None
