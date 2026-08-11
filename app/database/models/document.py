"""Document persistence model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Document(Base):
    """Persisted metadata, content, and extraction details for an upload."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(200), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    extension: Mapped[str] = mapped_column(String(32), nullable=False)
    extraction_method: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    character_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    requires_vision_pages: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    warnings: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    image_content: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )

    pages: Mapped[list["DocumentPage"]] = relationship(  # noqa: F821
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentPage.page_number",
        passive_deletes=True,
    )
