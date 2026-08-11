"""Resolve the document report generator from application settings."""

from app.core.config import settings
from app.core.exceptions import ApplicationConfigurationError
from app.documents.reporting import (
    DocumentReportGenerator,
    GeminiDocumentReportGenerator,
    MockDocumentReportGenerator,
)


def create_document_report_generator() -> DocumentReportGenerator:
    """Build a DocumentReportGenerator based on LLM_PROVIDER configuration."""
    provider = settings.LLM_PROVIDER.strip().lower()
    if provider == "mock":
        return MockDocumentReportGenerator()
    if provider == "gemini":
        return GeminiDocumentReportGenerator(
            model_name=settings.LLM_MODEL,
            api_key=settings.GEMINI_API_KEY,
        )
    raise ApplicationConfigurationError(
        f"Unsupported LLM_PROVIDER '{settings.LLM_PROVIDER}' for document "
        "report generation. Supported values: 'mock', 'gemini'."
    )


__all__ = ["create_document_report_generator"]
