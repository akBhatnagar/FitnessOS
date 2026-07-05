"""Workout domain models: exercises, plans, sessions, and history."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class MuscleGroup(str, Enum):
    CHEST = "chest"
    BACK = "back"
    SHOULDERS = "shoulders"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    FOREARMS = "forearms"
    CORE = "core"
    QUADS = "quads"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CALVES = "calves"
    FULL_BODY = "full_body"
    CARDIO = "cardio"


class ExerciseType(str, Enum):
    COMPOUND = "compound"
    ISOLATION = "isolation"
    CARDIO = "cardio"
    STRETCHING = "stretching"
    PLYOMETRIC = "plyometric"


class WorkoutPhase(str, Enum):
    HYPERTROPHY = "hypertrophy"
    STRENGTH = "strength"
    CUTTING = "cutting"
    DELOAD = "deload"
    MAINTENANCE = "maintenance"
    PEAK = "peak"


class SessionStatus(str, Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    MISSED = "missed"
    SKIPPED = "skipped"


class Exercise(UUIDMixin, TimestampMixin, Base):
    """
    Master exercise library — shared across all users.

    Exercises are global (not user-specific). User-specific preferences
    (liked/disliked) are stored in UserPreferences.
    """

    __tablename__ = "exercises"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    exercise_type: Mapped[ExerciseType] = mapped_column(String(50), nullable=False)
    primary_muscle: Mapped[MuscleGroup] = mapped_column(String(50), nullable=False)
    secondary_muscles: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    equipment_needed: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    instructions: Mapped[str | None] = mapped_column(Text)
    tips: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str | None] = mapped_column(String(1024))
    is_compound: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    met_value: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))  # for calorie calculation
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    history: Mapped[list] = relationship("ExerciseHistory", back_populates="exercise")
    workout_sets: Mapped[list] = relationship("WorkoutSet", back_populates="exercise")

    def __repr__(self) -> str:
        return f"<Exercise {self.name}>"


class WorkoutPlan(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    A structured training program (e.g. PPL, Upper/Lower, Bro Split).

    Plans contain multiple WorkoutSessions organized by day of week.
    The Workout Agent creates and manages plans; the Scheduler Agent
    slots them into the user's calendar.
    """

    __tablename__ = "workout_plans"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    phase: Mapped[WorkoutPhase] = mapped_column(String(50), nullable=False)
    duration_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    days_per_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plan_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    user: Mapped = relationship("User", back_populates="workout_plans")
    sessions: Mapped[list] = relationship(
        "WorkoutSession", back_populates="plan", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<WorkoutPlan {self.name} phase={self.phase}>"


class WorkoutSession(UUIDMixin, TimestampMixin, Base):
    """
    A single training session — either scheduled or logged after completion.

    Stores the planned structure and the actual performance separately
    to enable progressive overload calculations and adherence tracking.
    """

    __tablename__ = "workout_sessions"

    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workout_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    session_name: Mapped[str] = mapped_column(String(255), nullable=False)
    muscle_groups_targeted: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    status: Mapped[SessionStatus] = mapped_column(
        String(50), default=SessionStatus.SCHEDULED, nullable=False, index=True
    )

    # Actual performance data
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    calories_burned: Mapped[int | None] = mapped_column(Integer)

    # Post-session feedback
    effort_rating: Mapped[int | None] = mapped_column(Integer)  # 1-10
    fatigue_rating: Mapped[int | None] = mapped_column(Integer)  # 1-10
    mood_rating: Mapped[int | None] = mapped_column(Integer)  # 1-10
    notes: Mapped[str | None] = mapped_column(Text)

    plan: Mapped = relationship("WorkoutPlan", back_populates="sessions")
    sets: Mapped[list] = relationship(
        "WorkoutSet", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<WorkoutSession {self.session_name} on {self.scheduled_date}>"


class WorkoutSet(UUIDMixin, TimestampMixin, Base):
    """Individual set within a workout session."""

    __tablename__ = "workout_sets"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exercises.id"),
        nullable=False,
        index=True,
    )
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Planned targets
    planned_reps: Mapped[int | None] = mapped_column(Integer)
    planned_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    planned_duration_seconds: Mapped[int | None] = mapped_column(Integer)

    # Actual performance
    actual_reps: Mapped[int | None] = mapped_column(Integer)
    actual_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    actual_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    rpe: Mapped[int | None] = mapped_column(Integer)  # Rate of Perceived Exertion 1-10
    notes: Mapped[str | None] = mapped_column(Text)

    session: Mapped = relationship("WorkoutSession", back_populates="sets")
    exercise: Mapped = relationship("Exercise", back_populates="workout_sets")


class ExerciseHistory(UUIDMixin, TimestampMixin, Base):
    """
    Personal records and progression history per exercise.

    Maintained by the Workout Agent to enable progressive overload
    and detect strength gains or regressions.
    """

    __tablename__ = "exercise_history"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exercises.id"),
        nullable=False,
        index=True,
    )
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Best performance on this date
    best_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    best_reps: Mapped[int | None] = mapped_column(Integer)
    estimated_1rm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))  # Epley formula
    total_volume_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    is_personal_record: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    exercise: Mapped = relationship("Exercise", back_populates="history")
