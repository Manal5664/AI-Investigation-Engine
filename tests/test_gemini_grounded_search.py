import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, call, patch

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import ApplicationConfigurationError
from app.main import app
from app.research.search.factory import create_search_provider
from app.research.search.base import SearchProviderRateLimitError
from app.research.search.gemini_grounded_provider import (
    GeminiGroundedSearchProvider,
)
from app.schemas.research import SearchResult
from app.schemas.source import SourceType
from app.services.web_research_service import WebResearchService


RETRIEVED_AT = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
SUMMARY = (
    "Official reporting describes current storage programs. "
    "Independent reporting identifies implementation constraints."
)


def _annotation(
    url: str | None,
    title: str | None,
    start_index: int | None,
    end_index: int | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        type="url_citation",
        url=url,
        title=title,
        start_index=start_index,
        end_index=end_index,
    )


def _interaction(
    annotations: list[Any] | None = None,
    *,
    summary: str = SUMMARY,
    include_search_metadata: bool = True,
) -> SimpleNamespace:
    steps: list[Any] = []
    if include_search_metadata:
        steps.extend(
            [
                SimpleNamespace(
                    type="google_search_call",
                    arguments=SimpleNamespace(
                        queries=[
                            "long duration energy storage official update",
                            "long duration storage implementation constraints",
                        ]
                    ),
                ),
                SimpleNamespace(
                    type="google_search_result",
                    result=[
                        {
                            "search_suggestions": (
                                "<div>Google Search suggestions</div>"
                            )
                        }
                    ],
                ),
            ]
        )
    steps.append(
        SimpleNamespace(
            type="model_output",
            content=[
                SimpleNamespace(
                    type="text",
                    text=summary,
                    annotations=annotations or [],
                )
            ],
        )
    )
    return SimpleNamespace(steps=steps, output_text=summary)


def _default_annotations() -> list[SimpleNamespace]:
    first_end = SUMMARY.index("Independent") - 1
    return [
        _annotation(
            "https://Example.GOV/storage/report"
            "?utm_source=gemini#findings",
            "Example Government Storage Report",
            0,
            first_end,
        ),
        _annotation(
            "https://www.reuters.com/business/energy/storage"
            "?view=full&region=us",
            "Reuters energy report",
            first_end + 1,
            len(SUMMARY),
        ),
    ]


def _provider(
    interaction: SimpleNamespace,
    *,
    side_effect: list[Any] | None = None,
    sleep: AsyncMock | None = None,
) -> tuple[GeminiGroundedSearchProvider, AsyncMock]:
    create_interaction = (
        AsyncMock(side_effect=side_effect)
        if side_effect is not None
        else AsyncMock(return_value=interaction)
    )
    client = SimpleNamespace(
        aio=SimpleNamespace(
            interactions=SimpleNamespace(create=create_interaction)
        )
    )
    provider = GeminiGroundedSearchProvider(
        model_name="gemini-3.6-flash",
        api_key="test-api-key",
        client=client,
        clock=lambda: RETRIEVED_AT,
        sleep=sleep,
    )
    return provider, create_interaction


class RateLimitError(Exception):
    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        body: Any = None,
    ) -> None:
        super().__init__("Gemini quota exhausted")
        self.status_code = 429
        self.body = body
        self.response = SimpleNamespace(headers=headers or {})


class ResourceExhaustedError(Exception):
    def __init__(self, details: Any) -> None:
        super().__init__("Gemini request unavailable")
        self.status = "RESOURCE_EXHAUSTED"
        self.details = details


def test_grounded_sources_are_parsed_and_normalized() -> None:
    provider, create_interaction = _provider(
        _interaction(_default_annotations())
    )

    response = asyncio.run(
        provider.search_with_context(
            "Research long-duration energy storage developments",
            5,
        )
    )

    assert response.provider_used == "gemini_grounded"
    assert response.model_used == "gemini-3.6-flash"
    assert response.grounded_summary == SUMMARY
    assert len(response.results) == 2
    assert all(
        isinstance(result, SearchResult)
        for result in response.results
    )
    assert str(response.results[0].url) == (
        "https://example.gov/storage/report"
    )
    assert response.results[0].title == (
        "Example Government Storage Report"
    )
    assert response.results[0].retrieved_at == RETRIEVED_AT
    assert response.results[0].source_type is SourceType.GOVERNMENT
    assert response.results[1].source_type is SourceType.NEWS
    assert response.grounding_metadata.search_queries
    assert response.grounding_metadata.search_suggestions_html
    assert len(response.grounding_metadata.citations) == 2

    call = create_interaction.await_args
    assert call is not None
    assert call.kwargs["model"] == "gemini-3.6-flash"
    assert call.kwargs["tools"] == [{"type": "google_search"}]
    assert "Do not provide a final truth verdict" in call.kwargs["input"]


def test_grounded_search_immediate_success_does_not_sleep() -> None:
    sleep = AsyncMock()
    provider, create_interaction = _provider(
        _interaction(_default_annotations()),
        sleep=sleep,
    )

    response = asyncio.run(
        provider.search_with_context(
            "Research immediate grounded search success",
            5,
        )
    )

    assert response.results
    assert create_interaction.await_count == 1
    sleep.assert_not_awaited()


def test_grounded_search_retries_rate_limit_then_succeeds() -> None:
    sleep = AsyncMock()
    interaction = _interaction(_default_annotations())
    provider, create_interaction = _provider(
        interaction,
        side_effect=[
            RateLimitError(headers={"retry-after": "1.5"}),
            interaction,
        ],
        sleep=sleep,
    )

    response = asyncio.run(
        provider.search_with_context(
            "Research rate-limited grounded search recovery",
            5,
        )
    )

    assert response.results
    assert create_interaction.await_count == 2
    sleep.assert_awaited_once_with(1.5)


def test_grounded_search_repeated_rate_limits_exhaust_attempts() -> None:
    sleep = AsyncMock()
    rate_limits = [RateLimitError() for _ in range(3)]
    provider, create_interaction = _provider(
        _interaction(),
        side_effect=rate_limits,
        sleep=sleep,
    )

    with pytest.raises(SearchProviderRateLimitError) as captured:
        asyncio.run(
            provider.search_with_context(
                "Research repeated grounded search rate limits",
                5,
            )
        )

    error = captured.value
    assert error.error_type == "rate_limit"
    assert error.provider == "gemini_grounded"
    assert error.model == "gemini-3.6-flash"
    assert error.retryable is True
    assert error.retry_after_seconds is None
    assert "API quota or rate limit was exhausted" in error.message
    assert create_interaction.await_count == 3
    assert sleep.await_args_list == [call(1.0), call(2.0)]


def test_resource_exhausted_error_preserves_retry_metadata() -> None:
    sleep = AsyncMock()
    details = {
        "error": {
            "status": "RESOURCE_EXHAUSTED",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.RetryInfo",
                    "retryDelay": "4.5s",
                }
            ],
        }
    }
    provider, _ = _provider(
        _interaction(),
        side_effect=[ResourceExhaustedError(details) for _ in range(3)],
        sleep=sleep,
    )

    with pytest.raises(SearchProviderRateLimitError) as captured:
        asyncio.run(
            provider.search_with_context(
                "Research RESOURCE_EXHAUSTED retry metadata",
                5,
            )
        )

    assert captured.value.retry_after_seconds == 4.5
    assert captured.value.retryable is True
    assert sleep.await_args_list == [call(4.5), call(4.5)]


def test_rate_limit_failure_does_not_fabricate_sources() -> None:
    sleep = AsyncMock()
    provider, create_interaction = _provider(
        _interaction(),
        side_effect=[RateLimitError() for _ in range(3)],
        sleep=sleep,
    )

    with patch(
        "app.research.search.mock_provider."
        "MockSearchProvider.search_with_context",
        new_callable=AsyncMock,
    ) as mock_search:
        with pytest.raises(SearchProviderRateLimitError):
            asyncio.run(
                WebResearchService(provider).research(
                    "Research grounded failure without fake sources",
                    max_results=5,
                )
            )

    assert create_interaction.await_count == 3
    mock_search.assert_not_awaited()


def test_grounded_provider_requires_api_key() -> None:
    with pytest.raises(
        ApplicationConfigurationError,
        match="GEMINI_API_KEY is required",
    ):
        GeminiGroundedSearchProvider(
            model_name="gemini-3.6-flash",
            api_key=None,
        )


def test_no_grounding_metadata_returns_no_sources() -> None:
    ungrounded_summary = (
        "The model mentioned https://not-grounded.example/article in text."
    )
    provider, _ = _provider(
        _interaction(
            [],
            summary=ungrounded_summary,
            include_search_metadata=False,
        )
    )

    response = asyncio.run(
        provider.search_with_context(
            "Research a topic without usable citations",
            5,
        )
    )

    assert response.results == []
    assert response.grounding_metadata.citations == []
    assert all(
        "not-grounded.example" not in str(result.url)
        for result in response.results
    )
    assert any(
        "no usable source metadata" in warning
        for warning in response.warnings
    )


def test_duplicate_urls_are_deduplicated_after_normalization() -> None:
    annotations = [
        _annotation(
            "https://example.gov/report?utm_source=first#one",
            "Government report",
            0,
            20,
        ),
        _annotation(
            "https://EXAMPLE.gov/report",
            "Government report",
            21,
            40,
        ),
    ]
    provider, _ = _provider(_interaction(annotations))

    response = asyncio.run(
        provider.search_with_context(
            "Research duplicate grounded source handling",
            5,
        )
    )

    assert len(response.results) == 1
    assert len(response.grounding_metadata.citations) == 2
    assert (
        response.results[0].metadata.grounding_citation_count == 2
    )
    assert any("Deduplicated 1" in warning for warning in response.warnings)


def test_malformed_grounding_metadata_is_ignored() -> None:
    annotations: list[Any] = [
        _annotation(
            "javascript:alert(1)",
            "Unsafe source",
            0,
            10,
        ),
        _annotation(
            "https://missing-title.example/article",
            None,
            0,
            10,
        ),
        {"type": "url_citation", "title": "Missing URL"},
        _annotation(
            "https://valid.example/article",
            "Valid grounded source",
            999,
            1000,
        ),
    ]
    provider, _ = _provider(_interaction(annotations))

    response = asyncio.run(
        provider.search_with_context(
            "Research malformed grounding metadata handling",
            5,
        )
    )

    assert [str(result.url) for result in response.results] == [
        "https://valid.example/article"
    ]
    assert response.results[0].snippet is None
    assert any("malformed" in warning for warning in response.warnings)
    assert any("invalid text offsets" in warning for warning in response.warnings)


def test_grounded_provider_factory_selection() -> None:
    config = replace(
        settings,
        SEARCH_PROVIDER="gemini_grounded",
        SEARCH_MODEL="configured-search-model",
        GEMINI_API_KEY="test-api-key",
        LLM_TIMEOUT_SECONDS=20,
    )
    sentinel_provider = object()

    with patch(
        "app.research.search.factory.GeminiGroundedSearchProvider",
        return_value=sentinel_provider,
    ) as provider_class:
        provider = create_search_provider(config=config)

    assert provider is sentinel_provider
    provider_class.assert_called_once_with(
        model_name="configured-search-model",
        api_key="test-api-key",
        timeout_seconds=20,
    )


def test_web_research_service_preserves_source_provenance() -> None:
    provider, _ = _provider(_interaction(_default_annotations()))

    result = asyncio.run(
        WebResearchService(provider).research(
            "Research long-duration energy storage developments",
            max_results=5,
        )
    )

    assert len(result.sources) == 2
    assert all(source.credibility is not None for source in result.sources)
    first_source = result.sources[0]
    assert first_source.retrieved_at == RETRIEVED_AT
    assert (
        first_source.metadata.retrieval_provider
        == "gemini_grounded"
    )
    assert first_source.metadata.retrieval_model == "gemini-3.6-flash"
    assert first_source.metadata.retrieval_query == result.query
    source_ids = {source.source_id for source in result.sources}
    assert {
        citation.source_id
        for citation in result.grounding_metadata.citations
    } <= source_ids
    assert all(
        str(citation.source_url)
        in {str(source.url) for source in result.sources}
        for citation in result.grounding_metadata.citations
    )


def test_web_research_api_response() -> None:
    provider, _ = _provider(_interaction(_default_annotations()))

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
                        "Research long-duration energy storage developments"
                    ),
                    "max_results": 2,
                },
            )

    with patch(
        "app.api.v1.research_routes.create_search_provider",
        return_value=provider,
    ):
        response = asyncio.run(make_request())

    payload = response.json()
    assert response.status_code == 200
    assert payload["provider_used"] == "gemini_grounded"
    assert payload["model_used"] == "gemini-3.6-flash"
    assert len(payload["sources"]) == 2
    assert payload["grounded_summary"] == SUMMARY
    assert payload["grounding_metadata"]["citations"]
    assert all(source["credibility"] for source in payload["sources"])
    assert "evidence_items" not in payload
