from app.core.exceptions import ApplicationConfigurationError
from app.research.search.base import SearchProvider
from app.research.search.mock_provider import MockSearchProvider


def create_search_provider(provider_name: str = "mock") -> SearchProvider:
    normalized_name = provider_name.strip().casefold()
    if normalized_name == "mock":
        return MockSearchProvider()

    raise ApplicationConfigurationError(
        "Unsupported search provider "
        f"'{provider_name}'. Supported providers: mock."
    )
