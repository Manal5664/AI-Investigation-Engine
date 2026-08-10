from app.core.config import Settings, settings
from app.core.exceptions import ApplicationConfigurationError
from app.rag.embeddings.base import EmbeddingProvider
from app.rag.embeddings.gemini_provider import GeminiEmbeddingProvider
from app.rag.embeddings.mock_provider import MockEmbeddingProvider


def create_embedding_provider(
    provider_name: str | None = None,
    config: Settings | None = None,
) -> EmbeddingProvider:
    active_config = config or settings
    requested_provider = provider_name or active_config.EMBEDDING_PROVIDER
    normalized_name = requested_provider.strip().casefold()

    if normalized_name == "mock":
        return MockEmbeddingProvider(
            model_name=active_config.EMBEDDING_MODEL,
        )
    if normalized_name == "gemini":
        return GeminiEmbeddingProvider(
            model_name=active_config.EMBEDDING_MODEL,
            api_key=active_config.GEMINI_API_KEY,
            timeout_seconds=active_config.LLM_TIMEOUT_SECONDS,
        )
    raise ApplicationConfigurationError(
        "Unsupported embedding provider "
        f"'{requested_provider}'. Supported providers: mock, gemini."
    )
