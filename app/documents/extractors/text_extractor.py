"""Extractors for text (txt/md) documents.

Since .txt and .md files never contain executable content, extraction is
pure text handling and page-preservation is trivial (a single page).
"""

from app.documents.base import DocumentExtractor
from app.documents.models import (
    DocumentKind,
    ExtractedDocument,
    ExtractedPage,
    ExtractedSection,
    UploadedDocument,
)


class TextExtractor(DocumentExtractor):
    """Extract content from plain-text and markdown documents."""

    @property
    def kind(self) -> str:
        return DocumentKind.TEXT.value

    async def extract(
        self,
        uploaded: UploadedDocument,
        content: bytes,
        *,
        max_pages: int,
    ) -> ExtractedDocument:
        decoded = content.decode("utf-8", errors="replace")
        decoded = decoded.replace("\r\n", "\n").replace("\r", "\n")
        text = decoded.lstrip("\ufeff")

        page = ExtractedPage(
            page_number=1,
            text=text,
            sections=self._split_sections(text),
        )
        return ExtractedDocument(
            document_id=uploaded.document_id,
            filename=uploaded.filename,
            mime_type=uploaded.mime_type,
            file_size_bytes=uploaded.file_size_bytes,
            content_hash=uploaded.content_hash,
            kind=uploaded.kind,
            extraction_method="text",
            extracted_at=uploaded.received_at,
            pages=[page],
        )

    @staticmethod
    def _split_sections(text: str) -> list[ExtractedSection]:
        """Split markdown text into heading-delimited sections."""
        lines = text.splitlines()
        if not lines:
            return []

        def offset_of(line_index: int) -> int:
            return sum(len(line) + 1 for line in lines[:line_index])

        sections: list[ExtractedSection] = []
        start = 0
        order = 0
        for index, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("#"):
                continue
            heading = stripped.lstrip("#").strip()
            if not heading:
                continue
            if index > start and "\n".join(lines[start:index]).strip():
                sections.append(
                    ExtractedSection(
                        heading=None,
                        text="\n".join(lines[start:index]).strip(),
                        order_index=order,
                        character_start=offset_of(start),
                        character_end=offset_of(index),
                    )
                )
                order += 1
            sections.append(
                ExtractedSection(
                    heading=heading,
                    text=heading,
                    order_index=order,
                    character_start=offset_of(index),
                    character_end=offset_of(index) + len(heading),
                )
            )
            order += 1
            start = index + 1

        tail = "\n".join(lines[start:]).strip()
        if tail:
            sections.append(
                ExtractedSection(
                    heading=None,
                    text=tail,
                    order_index=order,
                    character_start=offset_of(start),
                    character_end=offset_of(len(lines)),
                )
            )
        return sections


__all__ = ["TextExtractor"]
