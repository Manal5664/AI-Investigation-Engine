"""Extractor for image documents.

Images are passed to a vision provider (typically a multimodal model) to
produce a description, any visible text, and a list of objects. Pillow is
used only to sanity-check the file and downscale oversized images; no
server-side rendering of untrusted markup ever happens.
"""

from app.documents.base import DocumentExtractionError, DocumentExtractor
from app.documents.models import (
    DocumentKind,
    ExtractedDocument,
    ExtractedImageContent,
    UploadedDocument,
)

MAX_IMAGE_DIMENSION = 4096


class ImageExtractor(DocumentExtractor):
    """Extract image content via a vision provider."""

    def __init__(self, vision_provider) -> None:
        self._vision = vision_provider

    @property
    def kind(self) -> str:
        return DocumentKind.IMAGE.value

    async def extract(
        self,
        uploaded: UploadedDocument,
        content: bytes,
        *,
        max_pages: int,
    ) -> ExtractedDocument:
        normalized = self._normalize(content, uploaded.filename)
        image_content = await self._vision.describe(
            image_bytes=normalized,
            mime_type=uploaded.mime_type,
            filename=uploaded.filename,
        )
        return ExtractedDocument(
            document_id=uploaded.document_id,
            filename=uploaded.filename,
            mime_type=uploaded.mime_type,
            file_size_bytes=uploaded.file_size_bytes,
            content_hash=uploaded.content_hash,
            kind=uploaded.kind,
            extraction_method=f"vision_{self._vision.provider_name}",
            extracted_at=uploaded.received_at,
            image_content=image_content,
            warnings=[] if image_content.visible_text else [
                "vision provider returned no visible text; description only"
            ],
        )

    def _normalize(self, content: bytes, filename: str) -> bytes:
        try:
            from PIL import Image
            from io import BytesIO

            with Image.open(BytesIO(content)) as image:
                if max(image.size) <= MAX_IMAGE_DIMENSION:
                    return content
                image.thumbnail(
                    (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                    Image.Resampling.LANCZOS,
                )
                buffer = BytesIO()
                image.save(
                    buffer,
                    format="PNG" if image.mode in ("RGBA", "LA") else "JPEG",
                )
                return buffer.getvalue()
        except DocumentExtractionError:
            raise
        except Exception as exc:
            raise DocumentExtractionError(
                f"image '{filename}' could not be decoded: {exc}"
            ) from exc


__all__ = ["ImageExtractor"]
