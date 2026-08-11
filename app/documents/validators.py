"""Validate raw upload bytes before they are handed to an extractor.

Validation never reads file content beyond what the OS mime sniffing and
the extraction pipeline itself needs, so uploaded material is not executed
or rendered as markup.
"""

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.documents.base import DocumentValidationError
from app.documents.models import DocumentKind, UploadedDocument

SUPPORTED_EXTENSIONS: dict[str, DocumentKind] = {
    ".pdf": DocumentKind.PDF,
    ".docx": DocumentKind.DOCX,
    ".txt": DocumentKind.TEXT,
    ".md": DocumentKind.TEXT,
    ".png": DocumentKind.IMAGE,
    ".jpg": DocumentKind.IMAGE,
    ".jpeg": DocumentKind.IMAGE,
}

DETECTED_MIME_TO_KIND: dict[str, DocumentKind] = {
    "application/pdf": DocumentKind.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        DocumentKind.DOCX
    ),
    "text/plain": DocumentKind.TEXT,
    "text/markdown": DocumentKind.TEXT,
    "image/png": DocumentKind.IMAGE,
    "image/jpeg": DocumentKind.IMAGE,
}


@dataclass(frozen=True)
class ValidatedUpload:
    uploaded: UploadedDocument
    content: bytes


def _kind_from_extension(filename: str) -> DocumentKind | None:
    ext = (mimetypes.guess_extension(mimetypes.guess_type(filename)[0] or "")
           or f".{filename.rsplit('.', 1)[-1].lower()}"
           if "." in filename else "")
    if ext in SUPPORTED_EXTENSIONS:
        return SUPPORTED_EXTENSIONS[ext]
    suffix = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""
    return SUPPORTED_EXTENSIONS.get(suffix)


def _mime_to_kind(mime_type: str) -> DocumentKind | None:
    normalized = (mime_type or "").split(";")[0].strip().lower()
    return DETECTED_MIME_TO_KIND.get(normalized)


def _file_size_bytes(content: bytes) -> int:
    return len(content)


def validate_upload(
    *,
    filename: str,
    content: bytes,
    max_bytes: int,
    mime_type: str | None = None,
) -> ValidatedUpload:
    """Validate a single document upload and derive its metadata."""
    if not filename or not filename.strip():
        raise DocumentValidationError("document filename must not be empty")
    filename = filename.strip()

    if not content:
        raise DocumentValidationError(f"document '{filename}' is empty")

    size = _file_size_bytes(content)
    if size > max_bytes:
        raise DocumentValidationError(
            f"document '{filename}' is {size} bytes; the maximum "
            f"allowed is {max_bytes} bytes"
        )

    if not mime_type or not mime_type.strip():
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    detected_kind = _mime_to_kind(mime_type) or _kind_from_extension(filename)
    if detected_kind is None:
        raise DocumentValidationError(
            f"document '{filename}' has unsupported type '{mime_type}'"
        )

    ext = mimetypes.guess_extension(mime_type) or f".{filename.rsplit('.', 1)[-1].lower()}"
    if detected_kind == DocumentKind.TEXT and ext not in {".txt", ".md", ".text"}:
        ext = ".txt"

    document_id = f"doc-{uuid4().hex}"
    uploaded = UploadedDocument(
        document_id=document_id,
        filename=filename,
        mime_type=mime_type,
        file_size_bytes=size,
        content_hash=hashlib.sha256(content).hexdigest(),
        kind=detected_kind,
        extension=ext,
        received_at=datetime.now(timezone.utc),
    )
    return ValidatedUpload(uploaded=uploaded, content=content)


__all__ = [
    "SUPPORTED_EXTENSIONS",
    "ValidatedUpload",
    "validate_upload",
]
