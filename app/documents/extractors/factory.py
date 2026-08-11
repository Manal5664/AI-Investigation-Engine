"""Registry that maps a document kind to its extractor implementation."""

from app.documents.base import DocumentExtractor, DocumentExtractionError
from app.documents.extractors.docx_extractor import DocxExtractor
from app.documents.extractors.image_extractor import ImageExtractor
from app.documents.extractors.pdf_extractor import PdfExtractor
from app.documents.extractors.text_extractor import TextExtractor
from app.documents.models import DocumentKind


class ExtractorFactory:
    """Resolve the extractor responsible for a given document kind."""

    def __init__(self, vision_provider) -> None:
        self._extractors: dict[str, DocumentExtractor] = {
            DocumentKind.TEXT.value: TextExtractor(),
            DocumentKind.PDF.value: PdfExtractor(),
            DocumentKind.DOCX.value: DocxExtractor(),
            DocumentKind.IMAGE.value: ImageExtractor(vision_provider),
        }

    def get(self, kind: DocumentKind) -> DocumentExtractor:
        extractor = self._extractors.get(kind.value)
        if extractor is None:
            raise DocumentExtractionError(
                f"no extractor is registered for document kind '{kind.value}'"
            )
        return extractor


__all__ = ["ExtractorFactory"]
