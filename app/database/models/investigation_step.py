"""Audit-step persistence model."""

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


class InvestigationStep(Base):
    """One audit/replay step of an investigation, kept in execution order."""

    __tablename__ = "investigation_steps"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id",
            "step_id",
            name="uq_investigation_steps_investigation_id_step_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[str] = mapped_column(String(32), nullable=False)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    provider_used: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    model_used: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    action_summary: Mapped[str] = mapped_column(Text, nullable=False)
    input_references: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    output_references: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    warnings: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    errors: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )

    investigation: Mapped[Investigation] = relationship(
        back_populates="steps",
    )
