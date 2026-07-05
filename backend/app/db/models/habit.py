"""Habit tracking models."""

from __future__ import annotations

import uuid
from datetime import date
from enum import Enum

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text, Time
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class HabitFrequency(str, Enum):
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    CUSTOM = "custom"


class Habit(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """User-defined or AI-suggested habit to track."""

    __tablename__ = "habits"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[HabitFrequency] = mapped_column(String(50), nullable=False)
    active_days: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    target_time: Mapped = mapped_column(Time, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    streak_current: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    streak_best: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="general")
    ai_suggested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    logs: Mapped[list] = relationship(
        "HabitLog", back_populates="habit", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Habit {self.name} streak={self.streak_current}>"


class HabitLog(UUIDMixin, TimestampMixin, Base):
    """Daily completion log for a habit."""

    __tablename__ = "habit_logs"

    habit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("habits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    logged_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    habit: Mapped = relationship("Habit", back_populates="logs")
