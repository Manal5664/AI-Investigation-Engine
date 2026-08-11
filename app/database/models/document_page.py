"""Document-page persistence model."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class DocumentPage(Base):
    """One extracted page of a persisted document, with its sections."""

    __tablename__ = "document_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requires_vision: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    sections: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )

    document: Mapped[Document] = relationship(
        back_populates="pages",
    )
