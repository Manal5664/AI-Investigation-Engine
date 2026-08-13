import asyncio
import re
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, settings
from app.core.exceptions import ApplicationConfigurationError
from app.main import app
from app.research.search.factory import create_search_provider
from app.research.search.gemini_grounded_provider import (
    GeminiGroundedSearchProvider,
)
from app.research.search.mock_provider import MockSearchProvider
from app.schemas.research import SearchResult
from app.schemas.source import SourceType


def test_mock_search_provider_is_typed_and_deterministic() -> None:
    provider = MockSearchProvider()

    first = asyncio.run(provider.search("A valid research query", 4))
    second = asyncio.run(provider.search("A valid research query", 4))

    assert provider.provider_name == "mock"
    assert first == second
    assert len(first) == 4
    assert all(isinstance(result, SearchResult) for result in first)
    assert first[0].source_type is SourceType.ACADEMIC


def test_mock_search_provider_respects_date_filters() -> None:
    provider = MockSearchProvider()
    published_after = datetime(2026, 1, 1, tzinfo=UTC)

    results = asyncio.run(
        provider.search(
            "A valid research query",
            8,
            published_after=published_after,
        )
    )

    assert results
    assert all(result.published_at is not None for result in results)
    assert all(
        result.published_at >= published_after
        for result in results
        if result.published_at is not None
    )


def test_search_factory_accepts_mock_and_rejects_unknown_provider() -> None:
    assert isinstance(create_search_provider("mock"), MockSearchProvider)

    with pytest.raises(Exception, match="Unsupported search provider"):
        create_search_provider("paid-provider")


def test_search_factory_uses_configured_provider_when_none_supplied() -> None:
    mock_config = replace(settings, SEARCH_PROVIDER="mock")
    assert isinstance(
        create_search_provider(config=mock_config),
        MockSearchProvider,
    )

    gemini_config = replace(
        settings,
        SEARCH_PROVIDER="gemini_grounded",
        GEMINI_API_KEY="test-only-key",
    )
    provider = create_search_provider(config=gemini_config)
    assert isinstance(provider, GeminiGroundedSearchProvider)
    assert provider.provider_name == "gemini_grounded"
    assert provider.model_name == settings.SEARCH_MODEL


def test_search_factory_gemini_grounded_requires_api_key() -> None:
    gemini_config = replace(
        settings,
        SEARCH_PROVIDER="gemini_grounded",
        GEMINI_API_KEY=None,
    )
    with pytest.raises(
        ApplicationConfigurationError,
        match="GEMINI_API_KEY is required",
    ):
        create_search_provider(config=gemini_config)


def test_no_hardcoded_gemini_provider_in_route_wiring() -> None:
    hard_coded = re.compile(
        r'create_search_provider\(\s*["\']gemini_grounded["\']\s*\)'
    )
    targets = [
        PROJECT_ROOT / "app" / "api" / "v1" / "routes.py",
        PROJECT_ROOT / "app" / "api" / "v1" / "research_routes.py",
        PROJECT_ROOT / "app" / "api" / "ui_routes.py",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        assert not hard_coded.search(text), (
            f"{path} hard-codes the gemini_grounded search provider; "
            "use create_search_provider() so SEARCH_PROVIDER is respected."
        )


def test_web_research_api_uses_configured_mock_provider() -> None:
    async def make_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/v1/research/web",
                json={
                    "query": (
                        "Research long-duration storage performance"
                    ),
                    "max_results": 2,
                },
            )

    with (
        patch(
            "app.research.search.factory.GeminiGroundedSearchProvider",
        ) as gemini_cls,
        patch(
            "app.research.search.factory.settings",
            replace(settings, SEARCH_PROVIDER="mock"),
        ),
    ):
        response = asyncio.run(make_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_used"] == "mock"
    assert len(payload["sources"]) >= 1
    gemini_cls.assert_not_called()


def test_search_result_rejects_malformed_url() -> None:
    with pytest.raises(ValidationError):
        SearchResult.model_validate(
            {
                "title": "Invalid URL result",
                "url": "not-a-url",
                "snippet": "A snippet long enough to be valid.",
                "source_type": "unknown",
                "retrieved_at": "2026-08-01T12:00:00Z",
            }
        )
