from datetime import datetime
from enum import Enum

from pydantic import Field, model_validator

from app.schemas.investigation import StrictModel


class DocumentKind(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    TEXT = "text"
    IMAGE = "image"


class DocumentProvenance(StrictModel):
    """Page/section provenance for extracted document content."""

    document_id: str = Field(pattern=r"^doc-[0-9a-f]{12,64}$")
    filename: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    file_size_bytes: int = Field(ge=0)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    location: str | None = None
    extraction_method: str = Field(min_length=1)
    extracted_at: datetime


class UploadedDocument(StrictModel):
    document_id: str = Field(pattern=r"^doc-[0-9a-f]{12,64}$")
    filename: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    file_size_bytes: int = Field(ge=0)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: DocumentKind
    extension: str = Field(min_length=1)
    received_at: datetime


class ExtractedSection(StrictModel):
    heading: str | None = None
    text: str = Field(min_length=1)
    order_index: int = Field(ge=0)
    character_start: int = Field(ge=0)
    character_end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> "ExtractedSection":
        if self.character_end <= self.character_start:
            raise ValueError(
                "character_end must be greater than character_start"
            )
        return self


class ExtractedPage(StrictModel):
    page_number: int = Field(ge=1)
    text: str = ""
    sections: list[ExtractedSection] = Field(default_factory=list)
    requires_vision: bool = False


class ExtractedImageContent(StrictModel):
    """Description, visible text, and objects read from an image."""

    description: str = Field(min_length=1)
    visible_text: str | None = None
    objects: list[str] = Field(default_factory=list)
    provider_used: str = Field(min_length=1)
    model_used: str = Field(min_length=1)
    requires_vision: bool = True


class ExtractedDocument(StrictModel):
    document_id: str = Field(pattern=r"^doc-[0-9a-f]{12,64}$")
    filename: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    file_size_bytes: int = Field(ge=0)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    kind: DocumentKind
    extraction_method: str = Field(min_length=1)
    extracted_at: datetime
    pages: list[ExtractedPage] = Field(default_factory=list)
    image_content: ExtractedImageContent | None = None
    warnings: list[str] = Field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def character_count(self) -> int:
        return sum(len(page.text) for page in self.pages)


class DocumentIngestionResult(StrictModel):
    document: UploadedDocument
    extracted: ExtractedDocument
    page_count: int = Field(ge=0)
    character_count: int = Field(ge=0)
    duplicate: bool = False
    warnings: list[str] = Field(default_factory=list)


class StoredDocument(StrictModel):
    uploaded: UploadedDocument
    extracted: ExtractedDocument
    content: bytes = Field(repr=False)


class DocumentStoreStats(StrictModel):
    store_type: str = Field(min_length=1)
    document_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    counts_by_kind: dict[str, int] = Field(default_factory=dict)


__all__ = [
    "DocumentIngestionResult",
    "DocumentKind",
    "DocumentProvenance",
    "DocumentStoreStats",
    "ExtractedDocument",
    "ExtractedImageContent",
    "ExtractedPage",
    "ExtractedSection",
    "StoredDocument",
    "UploadedDocument",
]
