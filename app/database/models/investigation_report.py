"""Investigation-report persistence model."""

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


class InvestigationReport(Base):
    """The synthesized, non-verdict report attached to an investigation."""

    __tablename__ = "investigation_reports"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id",
            name="uq_investigation_reports_investigation_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    overall_evidence_picture: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_rationale: Mapped[str] = mapped_column(
        Text, nullable=False, default=""
    )
    strongest_supporting_evidence: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    strongest_contradicting_evidence: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    unresolved_conflicts: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    important_limitations: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    alternative_explanations: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    evidence_gaps: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    investigation: Mapped[Investigation] = relationship(
        back_populates="report",
    )
