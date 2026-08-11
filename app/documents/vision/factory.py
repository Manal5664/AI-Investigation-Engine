"""Resolve the vision provider from application settings."""

from app.core.config import Settings
from app.core.exceptions import ApplicationConfigurationError
from app.documents.vision.base import VisionProvider
from app.documents.vision.gemini_provider import GeminiVisionProvider
from app.documents.vision.mock_provider import MockVisionProvider


def create_vision_provider(settings: Settings) -> VisionProvider:
    """Build a VisionProvider based on VISION_PROVIDER configuration."""
    provider = settings.VISION_PROVIDER.strip().lower()
    if provider == "mock":
        return MockVisionProvider()
    if provider == "gemini":
        return GeminiVisionProvider(
            model_name=settings.VISION_MODEL,
            api_key=settings.GEMINI_API_KEY,
        )
    raise ApplicationConfigurationError(
        f"Unsupported VISION_PROVIDER '{settings.VISION_PROVIDER}'. "
        "Supported values: 'mock', 'gemini'."
    )


__all__ = ["create_vision_provider"]
