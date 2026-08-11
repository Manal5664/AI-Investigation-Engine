"""Investigation aggregate persistence model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Investigation(Base):
    """Top-level record for a finished agentic investigation."""

    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_used: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    model_used: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    synthesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    warnings: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    errors: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    total_source_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    total_evidence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    plan: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )

    user: Mapped["User"] = relationship(  # noqa: F821
        back_populates="investigations",
    )
    steps: Mapped[list["InvestigationStep"]] = relationship(  # noqa: F821
        back_populates="investigation",
        cascade="all, delete-orphan",
        order_by="InvestigationStep.step_order",
        passive_deletes=True,
    )
    sources: Mapped[list["Source"]] = relationship(  # noqa: F821
        back_populates="investigation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    evidence_items: Mapped[list["EvidenceItem"]] = relationship(  # noqa: F821
        back_populates="investigation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    conflicts: Mapped[list["Conflict"]] = relationship(  # noqa: F821
        back_populates="investigation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    report: Mapped["InvestigationReport | None"] = relationship(  # noqa: F821
        back_populates="investigation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
