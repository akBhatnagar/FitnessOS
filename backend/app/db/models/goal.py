"""Goal model — tracks the user's fitness and lifestyle objectives."""

from __future__ import annotations

import uuid
from datetime import date
from enum import Enum

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class GoalCategory(str, Enum):
    FAT_LOSS = "fat_loss"
    MUSCLE_GAIN = "muscle_gain"
    STRENGTH = "strength"
    ENDURANCE = "endurance"
    AESTHETICS = "aesthetics"
    SWIMMING = "swimming"
    SLEEP = "sleep"
    NUTRITION = "nutrition"
    LIFESTYLE = "lifestyle"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    ACHIEVED = "achieved"
    PAUSED = "paused"
    ABANDONED = "abandoned"


class Goal(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Tracks a single user goal with measurable target and deadline.

    Multiple goals can be active simultaneously with different priorities.
    The AI reasoning pipeline always loads active goals before generating responses.
    """

    __tablename__ = "goals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[GoalCategory] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # Measurable target
    metric: Mapped[str | None] = mapped_column(String(100))  # e.g. "weight_kg", "body_fat_pct"
    current_value: Mapped[float | None] = mapped_column(Numeric(8, 2))
    target_value: Mapped[float | None] = mapped_column(Numeric(8, 2))
    unit: Mapped[str | None] = mapped_column(String(50))

    # Timeline
    target_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[GoalStatus] = mapped_column(
        String(50), default=GoalStatus.ACTIVE, nullable=False, index=True
    )
    achieved_at: Mapped[date | None] = mapped_column(Date)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped = relationship("User", back_populates="goals")

    def __repr__(self) -> str:
        return f"<Goal {self.category.value}: {self.title}>"
