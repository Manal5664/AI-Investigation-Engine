"""Source persistence model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Source(Base):
    """A normalized web/document source belonging to an investigation."""

    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id",
            "source_id",
            name="uq_sources_investigation_id_source_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    investigation_id: Mapped[str | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    publisher: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, default=dict
    )
    credibility: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )

    investigation: Mapped[Investigation] = relationship(
        back_populates="sources",
    )
