from app.core.config import Settings, settings
from app.core.exceptions import ApplicationConfigurationError
from app.documents.factory import get_document_store
from app.evidence.base import EvidenceExtractor
from app.evidence.gemini_extractor import GeminiEvidenceExtractor
from app.evidence.mock_extractor import MockEvidenceExtractor
from app.evidence.page_aware_extractor import PageAwareEvidenceExtractor


def create_evidence_extractor(
    provider_name: str | None = None,
    config: Settings | None = None,
) -> EvidenceExtractor:
    active_config = config or settings
    requested_provider = provider_name or active_config.EVIDENCE_PROVIDER
    normalized_name = requested_provider.strip().casefold()

    if normalized_name == "mock":
        base_extractor: EvidenceExtractor = MockEvidenceExtractor()
    elif normalized_name == "gemini":
        base_extractor = GeminiEvidenceExtractor(
            model_name=active_config.EVIDENCE_MODEL,
            api_key=active_config.GEMINI_API_KEY,
            timeout_seconds=active_config.LLM_TIMEOUT_SECONDS,
        )
    else:
        raise ApplicationConfigurationError(
            "Unsupported evidence provider "
            f"'{requested_provider}'. Supported providers: mock, gemini."
        )

    if active_config.EVIDENCE_INCLUDE_DOCUMENTS:
        from app.rag.embeddings.factory import create_embedding_provider
        from app.rag.vectorstore.factory import get_vector_store

        return PageAwareEvidenceExtractor(
            base_extractor,
            get_document_store(),
            embedding_provider=create_embedding_provider(),
            vector_store=get_vector_store(),
        )
    return base_extractor
