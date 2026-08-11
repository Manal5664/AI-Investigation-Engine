"""Extractor for PDF documents.

Extraction uses text and content streams already present in the PDF; no
JavaScript, external media, or network resources are executed or fetched.
Pages with no extractable text are flagged for vision-based reading.
"""

from app.documents.base import DocumentExtractionError, DocumentExtractor
from app.documents.models import (
    DocumentKind,
    ExtractedDocument,
    ExtractedPage,
    UploadedDocument,
)

PDF_HEADER = b"%PDF-"


def _safe_text(text: str | None) -> str:
    return (text or "").replace("\x00", " ")


class PdfExtractor(DocumentExtractor):
    """Extract page-preserving text from PDF documents."""

    def __init__(self) -> None:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - import guard
            raise DocumentExtractionError(
                "pypdf is not installed; install it to extract PDF documents"
            ) from exc
        self._reader = PdfReader

    @property
    def kind(self) -> str:
        return DocumentKind.PDF.value

    async def extract(
        self,
        uploaded: UploadedDocument,
        content: bytes,
        *,
        max_pages: int,
    ) -> ExtractedDocument:
        if not content.startswith(PDF_HEADER):
            raise DocumentExtractionError(
                f"document '{uploaded.filename}' is not a valid PDF"
            )
        try:
            reader = self._reader(__import__("io").BytesIO(content))
        except Exception as exc:
            raise DocumentExtractionError(
                f"document '{uploaded.filename}' could not be parsed as a PDF: {exc}"
            ) from exc

        pages = self._read_pages(reader, uploaded.filename, max_pages)
        return ExtractedDocument(
            document_id=uploaded.document_id,
            filename=uploaded.filename,
            mime_type=uploaded.mime_type,
            file_size_bytes=uploaded.file_size_bytes,
            content_hash=uploaded.content_hash,
            kind=uploaded.kind,
            extraction_method="pdf_text",
            extracted_at=uploaded.received_at,
            pages=pages,
        )

    def _read_pages(self, reader, filename: str, max_pages: int) -> list[ExtractedPage]:
        pages: list[ExtractedPage] = []
        for index, pdf_page in enumerate(reader.pages):
            if index >= max_pages:
                break
            text = _safe_text(pdf_page.extract_text())
            text = "\n".join(
                line.rstrip() for line in text.splitlines()
            ).strip()
            pages.append(
                ExtractedPage(
                    page_number=index + 1,
                    text=text,
                    requires_vision=not text,
                )
            )
        return pages


__all__ = ["PdfExtractor"]
