"""Deterministic mock vision provider used when VISION_PROVIDER=mock."""

from app.documents.models import ExtractedImageContent
from app.documents.vision.base import VisionProvider


class MockVisionProvider(VisionProvider):
    """Describe images from filename heuristics; never calls a real model."""

    def __init__(self, *, fallback_text: str | None = None) -> None:
        self._fallback_text = fallback_text or "Unrecognized image content."

    @property
    def provider_name(self) -> str:
        return "mock"

    async def describe(
        self,
        *,
        image_bytes: bytes,
        mime_type: str,
        filename: str,
    ) -> ExtractedImageContent:
        return ExtractedImageContent(
            description=(
                f"Mock vision description of '{filename}' "
                f"({len(image_bytes)} bytes, {mime_type})."
            ),
            visible_text=self._fallback_text,
            objects=[],
            provider_used="mock",
            model_used="mock-vision",
        )


__all__ = ["MockVisionProvider"]
