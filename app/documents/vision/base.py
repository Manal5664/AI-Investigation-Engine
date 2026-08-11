from abc import ABC, abstractmethod

from app.core.exceptions import ApplicationError
from app.documents.models import ExtractedImageContent


class VisionProviderError(ApplicationError):
    """Wrap failures from an upstream vision provider."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(
            message,
            code="vision_provider_error",
            status_code=status_code,
        )


class VisionProvider(ABC):
    """Describe an image and read visible text from it."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return a stable provider identifier."""

    @abstractmethod
    async def describe(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        filename: str,
    ) -> ExtractedImageContent:
        """Return a description, visible text, and objects for an image."""


__all__ = ["VisionProvider", "VisionProviderError"]
