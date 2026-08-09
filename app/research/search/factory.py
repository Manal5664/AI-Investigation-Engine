from app.core.config import Settings, settings
from app.core.exceptions import ApplicationConfigurationError
from app.research.search.base import SearchProvider
from app.research.search.gemini_grounded_provider import (
    GeminiGroundedSearchProvider,
)
from app.research.search.mock_provider import MockSearchProvider


def create_search_provider(
    provider_name: str | None = None,
    config: Settings | None = None,
) -> SearchProvider:
    active_config = config or settings
    requested_provider = provider_name or active_config.SEARCH_PROVIDER
    normalized_name = requested_provider.strip().casefold()
    if normalized_name == "mock":
        return MockSearchProvider()
    if normalized_name == "gemini_grounded":
        return GeminiGroundedSearchProvider(
            model_name=active_config.SEARCH_MODEL,
            api_key=active_config.GEMINI_API_KEY,
            timeout_seconds=active_config.LLM_TIMEOUT_SECONDS,
        )

    raise ApplicationConfigurationError(
        "Unsupported search provider "
        f"'{requested_provider}'. Supported providers: "
        "mock, gemini_grounded."
    )
