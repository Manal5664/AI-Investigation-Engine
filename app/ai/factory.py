from app.ai.base import LLMProvider
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

    raise ApplicationConfigurationError(
        "Unsupported LLM provider "
        f"'{active_config.LLM_PROVIDER}'. Supported providers: mock."
    )
