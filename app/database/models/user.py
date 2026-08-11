"""Persisted user entity."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class User(Base):
    """A persisted user record. Authentication/JWT are out of scope."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True
    )
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(
        String(200), nullable=False, default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    investigations: Mapped[list["Investigation"]] = relationship(  # noqa: F821
        back_populates="user",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"User(id={self.id!r}, email={self.email!r})"
