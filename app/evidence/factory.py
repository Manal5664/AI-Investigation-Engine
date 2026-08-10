from app.core.config import Settings, settings
from app.core.exceptions import ApplicationConfigurationError
from app.evidence.base import EvidenceExtractor
from app.evidence.gemini_extractor import GeminiEvidenceExtractor
from app.evidence.mock_extractor import MockEvidenceExtractor


def create_evidence_extractor(
    provider_name: str | None = None,
    config: Settings | None = None,
) -> EvidenceExtractor:
    active_config = config or settings
    requested_provider = provider_name or active_config.EVIDENCE_PROVIDER
    normalized_name = requested_provider.strip().casefold()

    if normalized_name == "mock":
        return MockEvidenceExtractor()
    if normalized_name == "gemini":
        return GeminiEvidenceExtractor(
            model_name=active_config.EVIDENCE_MODEL,
            api_key=active_config.GEMINI_API_KEY,
            timeout_seconds=active_config.LLM_TIMEOUT_SECONDS,
        )
    raise ApplicationConfigurationError(
        "Unsupported evidence provider "
        f"'{requested_provider}'. Supported providers: mock, gemini."
    )
