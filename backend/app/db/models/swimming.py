"""Swimming domain models: plans and session logs."""

from __future__ import annotations

import uuid
from datetime import date, time
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class SwimmingLevel(str, Enum):
    ABSOLUTE_BEGINNER = "absolute_beginner"
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    COMPETITIVE = "competitive"


class Stroke(str, Enum):
    FREESTYLE = "freestyle"
    BACKSTROKE = "backstroke"
    BREASTSTROKE = "breaststroke"
    BUTTERFLY = "butterfly"
    INDIVIDUAL_MEDLEY = "individual_medley"
    TREADING = "treading"
    FLOATING = "floating"


class SwimmingPlan(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Structured swimming progression plan.

    The Swimming Agent creates progressive plans starting from zero.
    Plans include breathing techniques, stroke progression, and endurance targets.
    """

    __tablename__ = "swimming_plans"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    current_level: Mapped[SwimmingLevel] = mapped_column(String(50), nullable=False)
    target_level: Mapped[SwimmingLevel] = mapped_column(String(50), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    sessions_per_week: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    session_duration_minutes: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Current milestones and focus areas
    current_focus: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    completed_milestones: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    plan_structure: Mapped[dict] = mapped_column(JSONB, default=dict)

    user: Mapped = relationship("User", back_populates="swimming_plans")
    sessions: Mapped[list] = relationship(
        "SwimmingSession", back_populates="plan", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SwimmingPlan {self.name} level={self.current_level}>"


class SwimmingSession(UUIDMixin, TimestampMixin, Base):
    """
    Log of a single swimming session.

    Tracks laps, strokes, breathing, and confidence — essential inputs
    for the Swimming Agent's progression algorithm.
    """

    __tablename__ = "swimming_sessions"

    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("swimming_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    session_time: Mapped[time | None] = mapped_column(Time)
    completed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Performance metrics
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    total_laps: Mapped[int | None] = mapped_column(Integer)
    total_meters: Mapped[int | None] = mapped_column(Integer)
    pool_length_m: Mapped[int] = mapped_column(Integer, default=25)
    strokes_practiced: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # Progression indicators (1-10 scale)
    breathing_comfort: Mapped[int | None] = mapped_column(Integer)
    confidence_level: Mapped[int | None] = mapped_column(Integer)
    technique_rating: Mapped[int | None] = mapped_column(Integer)
    endurance_rating: Mapped[int | None] = mapped_column(Integer)

    # Milestones achieved this session
    milestones_achieved: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    coach_feedback: Mapped[str | None] = mapped_column(Text)

    plan: Mapped = relationship("SwimmingPlan", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<SwimmingSession {self.session_date} {self.total_meters}m>"
