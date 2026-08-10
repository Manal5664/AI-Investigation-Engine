from app.core.config import Settings, settings
from app.core.exceptions import ApplicationConfigurationError
from app.graph.extraction.base import GraphExtractionProvider
from app.graph.extraction.gemini_extractor import GeminiGraphExtractionProvider
from app.graph.extraction.mock_extractor import MockGraphExtractionProvider


def create_graph_extraction_provider(
    provider_name: str | None = None,
    config: Settings | None = None,
) -> GraphExtractionProvider:
    active_config = config or settings
    requested_provider = (
        provider_name or active_config.GRAPH_EXTRACTION_PROVIDER
    )
    normalized_name = requested_provider.strip().casefold()
    if normalized_name == "mock":
        return MockGraphExtractionProvider()
    if normalized_name == "gemini":
        return GeminiGraphExtractionProvider(
            model_name=active_config.GRAPH_EXTRACTION_MODEL,
            api_key=active_config.GEMINI_API_KEY,
            timeout_seconds=active_config.LLM_TIMEOUT_SECONDS,
        )
    raise ApplicationConfigurationError(
        "Unsupported graph extraction provider "
        f"'{requested_provider}'. Supported providers: mock, gemini."
    )
