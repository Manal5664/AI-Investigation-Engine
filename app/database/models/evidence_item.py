"""Evidence-item persistence model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class EvidenceItem(Base):
    """A persisted evidence item with its full flattened provenance."""

    __tablename__ = "evidence_items"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id",
            "evidence_id",
            name="uq_evidence_items_investigation_id_evidence_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    investigation_id: Mapped[str | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    evidence_id: Mapped[str] = mapped_column(String(32), nullable=False)
    sub_question_id: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    stance: Mapped[str] = mapped_column(String(16), nullable=False)
    strength: Mapped[str] = mapped_column(String(16), nullable=False)

    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    relevant_passage: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    investigation: Mapped[Investigation] = relationship(
        back_populates="evidence_items",
    )
