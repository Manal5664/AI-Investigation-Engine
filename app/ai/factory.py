from app.ai.base import LLMProvider
from app.ai.gemini_provider import GeminiLLMProvider
from app.ai.mock_provider import MockLLMProvider
from app.core.config import Settings, settings
from app.core.exceptions import ApplicationConfigurationError


def create_llm_provider(
    config: Settings | None = None,
) -> LLMProvider:
    active_config = config or settings
    provider_name = active_config.LLM_PROVIDER.strip().casefold()

    if provider_name == "mock":
        return MockLLMProvider(model_name=active_config.LLM_MODEL)
    if provider_name == "gemini":
        return GeminiLLMProvider(
            model_name=active_config.LLM_MODEL,
            api_key=active_config.GEMINI_API_KEY,
            timeout_seconds=active_config.LLM_TIMEOUT_SECONDS,
        )

    raise ApplicationConfigurationError(
        "Unsupported LLM provider "
        f"'{active_config.LLM_PROVIDER}'. Supported providers: mock, gemini."
    )
