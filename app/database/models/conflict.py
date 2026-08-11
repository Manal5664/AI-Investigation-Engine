"""Conflict persistence model."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Conflict(Base):
    """A detected evidence conflict for one sub-question of an investigation."""

    __tablename__ = "conflicts"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id",
            "sub_question_id",
            name="uq_conflicts_investigation_id_sub_question_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    investigation_id: Mapped[str | None] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    sub_question_id: Mapped[str] = mapped_column(String(32), nullable=False)
    has_supporting_and_contradicting_evidence: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    unresolved_conflicts: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    conflicting_source_claims: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )

    investigation: Mapped[Investigation] = relationship(
        back_populates="conflicts",
    )
