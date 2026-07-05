"""Event model — milestone-aware planning (wedding, trips, festivals)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class EventType(str, Enum):
    WEDDING = "wedding"
    PRE_WEDDING = "pre_wedding"
    PHOTOSHOOT = "photoshoot"
    TRIP = "trip"
    VACATION = "vacation"
    FESTIVAL = "festival"
    SPORTS_EVENT = "sports_event"
    PHOTO_SHOOT = "photo_shoot"
    MEDICAL = "medical"
    OTHER = "other"


class PeakPhysicsPriority(str, Enum):
    """How aggressively to peak physique for this event."""
    MAINTAIN = "maintain"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    EXTREME = "extreme"


class Event(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Significant life event that influences training and nutrition planning.

    The Event Agent monitors all active events and automatically adjusts
    training phases, nutrition targets, and deload timing based on proximity.

    Days remaining is always calculated dynamically — never stored.
    """

    __tablename__ = "events"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[EventType] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # How this event should affect training
    peak_priority: Mapped[PeakPhysicsPriority] = mapped_column(
        String(50), default=PeakPhysicsPriority.MODERATE, nullable=False
    )
    deload_days_before: Mapped[int | None] = mapped_column()
    peak_week_start_days_before: Mapped[int | None] = mapped_column()

    # Event-specific planning metadata
    planning_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    user: Mapped = relationship("User", back_populates="events")

    @property
    def days_remaining(self) -> int:
        """Always calculated — never hardcoded or stored."""
        return (self.event_date - date.today()).days

    @property
    def is_upcoming(self) -> bool:
        return self.days_remaining > 0

    @property
    def is_critical(self) -> bool:
        """True if within 30 days — triggers aggressive adjustments."""
        return 0 < self.days_remaining <= 30

    def __repr__(self) -> str:
        return f"<Event {self.event_type.value}: {self.title} on {self.event_date}>"
