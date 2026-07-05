"""User and UserPreferences models."""

from __future__ import annotations

import uuid
from datetime import date, time
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class DietType(str, Enum):
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    NON_VEGETARIAN = "non_vegetarian"
    EGGETARIAN = "eggetarian"
    PESCATARIAN = "pescatarian"


class ActivityLevel(str, Enum):
    SEDENTARY = "sedentary"
    LIGHTLY_ACTIVE = "lightly_active"
    MODERATELY_ACTIVE = "moderately_active"
    VERY_ACTIVE = "very_active"
    EXTRA_ACTIVE = "extra_active"


class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Core user entity. Authentication is delegated to Clerk.

    The clerk_user_id is the external identifier from Clerk — it is used
    to link Clerk JWTs to internal user records without storing passwords.
    """

    __tablename__ = "users"

    clerk_user_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_onboarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    preferences: Mapped[UserPreferences | None] = relationship(
        "UserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    goals: Mapped[list] = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    events: Mapped[list] = relationship("Event", back_populates="user", cascade="all, delete-orphan")
    measurements: Mapped[list] = relationship("Measurement", back_populates="user", cascade="all, delete-orphan")
    workout_plans: Mapped[list] = relationship("WorkoutPlan", back_populates="user", cascade="all, delete-orphan")
    nutrition_plans: Mapped[list] = relationship("NutritionPlan", back_populates="user", cascade="all, delete-orphan")
    swimming_plans: Mapped[list] = relationship("SwimmingPlan", back_populates="user", cascade="all, delete-orphan")
    memories: Mapped[list] = relationship("MemoryStore", back_populates="user", cascade="all, delete-orphan")
    conversations: Mapped[list] = relationship("ConversationMessage", back_populates="user", cascade="all, delete-orphan")
    weekly_reviews: Mapped[list] = relationship("WeeklyReview", back_populates="user", cascade="all, delete-orphan")
    achievements: Mapped[list] = relationship("Achievement", back_populates="user", cascade="all, delete-orphan")
    coach_notes: Mapped[list] = relationship("CoachNote", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


class UserPreferences(UUIDMixin, TimestampMixin, Base):
    """
    Permanent memory layer for the user's personal profile.

    This is the most frequently read table — indexed heavily for fast retrieval
    during the AI reasoning pipeline initialization.
    """

    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_preferences_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ---- Physical Profile ----
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    current_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    target_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    # ---- Diet ----
    diet_type: Mapped[DietType] = mapped_column(
        String(50), default=DietType.VEGETARIAN, nullable=False
    )
    allowed_foods: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    disallowed_foods: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    food_allergies: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    supplement_preferences: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    meal_timing_preferences: Mapped[dict] = mapped_column(JSONB, default=dict)

    # ---- Schedule ----
    work_start_time: Mapped[time | None] = mapped_column(Time)
    work_end_time: Mapped[time | None] = mapped_column(Time)
    gym_preferred_time: Mapped[time | None] = mapped_column(Time)
    swim_preferred_time: Mapped[time | None] = mapped_column(Time)
    current_sleep_time: Mapped[time | None] = mapped_column(Time)
    target_sleep_time: Mapped[time | None] = mapped_column(Time)
    current_wake_time: Mapped[time | None] = mapped_column(Time)
    target_wake_time: Mapped[time | None] = mapped_column(Time)
    rest_days: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # ---- Training Preferences ----
    activity_level: Mapped[ActivityLevel] = mapped_column(
        String(50), default=ActivityLevel.MODERATELY_ACTIVE, nullable=False
    )
    preferred_exercises: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    disliked_exercises: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    current_injuries: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    medical_conditions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # ---- Motivation & Personality ----
    motivation_triggers: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    coaching_style_preference: Mapped[str] = mapped_column(
        String(50), default="encouraging"
    )

    # ---- Flexible metadata ----
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Relationship
    user: Mapped[User] = relationship("User", back_populates="preferences")

    def __repr__(self) -> str:
        return f"<UserPreferences user_id={self.user_id}>"
