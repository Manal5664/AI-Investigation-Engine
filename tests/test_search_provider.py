import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.research.search.factory import create_search_provider
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


def test_search_factory_supports_only_mock() -> None:
    assert isinstance(create_search_provider("mock"), MockSearchProvider)

    with pytest.raises(Exception, match="Unsupported search provider"):
        create_search_provider("paid-provider")


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
