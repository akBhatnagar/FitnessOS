"""Nutrition domain models: foods, recipes, meal plans, and logs."""

from __future__ import annotations

import uuid
from datetime import date, time
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class MealType(str, Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    PRE_WORKOUT = "pre_workout"
    POST_WORKOUT = "post_workout"
    SUPPLEMENT = "supplement"


class Food(UUIDMixin, TimestampMixin, Base):
    """
    Global food database.

    Foods are shared across all users. User-specific foods are flagged
    with is_user_created and linked via created_by_user_id.
    All nutritional values are per 100g unless noted.
    """

    __tablename__ = "food_database"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(255))
    barcode: Mapped[str | None] = mapped_column(String(50), index=True)
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_vegan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_gluten_free: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_user_created: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Macros per 100g
    calories_per_100g: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    protein_g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    carbs_g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    fiber_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    sugar_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    sodium_mg: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    calcium_mg: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    iron_mg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    serving_size_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    serving_description: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    meal_items: Mapped[list] = relationship("MealItem", back_populates="food")

    def __repr__(self) -> str:
        return f"<Food {self.name}>"


class Recipe(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    Recipe with ingredients and computed nutritional profile.

    Recipes can be AI-generated or user-defined.
    """

    __tablename__ = "recipes"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text)
    servings: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    prep_time_minutes: Mapped[int | None] = mapped_column(Integer)
    cook_time_minutes: Mapped[int | None] = mapped_column(Integer)
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    meal_type: Mapped[str | None] = mapped_column(String(50))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Computed totals per serving
    calories_per_serving: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    protein_g_per_serving: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    carbs_g_per_serving: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    fat_g_per_serving: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    ingredients: Mapped[dict] = mapped_column(JSONB, default=list)  # list of {food_id, grams}

    def __repr__(self) -> str:
        return f"<Recipe {self.name}>"


class NutritionPlan(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """
    A structured nutrition plan with daily macro targets.

    The Nutrition Agent creates and manages plans. Plans adapt automatically
    when the user's training phase, events, or adherence changes.
    """

    __tablename__ = "nutrition_plans"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Daily macro targets
    daily_calories: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_protein_g: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_carbs_g: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_fat_g: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_fiber_g: Mapped[int | None] = mapped_column(Integer)
    daily_water_ml: Mapped[int | None] = mapped_column(Integer)

    # Calorie cycling (higher on training days)
    training_day_calories: Mapped[int | None] = mapped_column(Integer)
    rest_day_calories: Mapped[int | None] = mapped_column(Integer)

    plan_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    user: Mapped = relationship("User", back_populates="nutrition_plans")
    meals: Mapped[list] = relationship(
        "Meal", back_populates="plan", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<NutritionPlan {self.name}>"


class Meal(UUIDMixin, TimestampMixin, Base):
    """Daily meal log entry."""

    __tablename__ = "meals"

    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nutrition_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    meal_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meal_time: Mapped[time | None] = mapped_column(Time)
    meal_type: Mapped[MealType] = mapped_column(String(50), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))

    # Computed totals (sum of MealItems)
    total_calories: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    total_protein_g: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    total_carbs_g: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    total_fat_g: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))

    notes: Mapped[str | None] = mapped_column(Text)
    restaurant_name: Mapped[str | None] = mapped_column(String(255))

    plan: Mapped = relationship("NutritionPlan", back_populates="meals")
    items: Mapped[list] = relationship(
        "MealItem", back_populates="meal", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Meal {self.meal_type} on {self.meal_date}>"


class MealItem(UUIDMixin, TimestampMixin, Base):
    """Individual food item within a meal."""

    __tablename__ = "meal_items"

    meal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    food_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("food_database.id"),
        nullable=True,
    )
    food_name: Mapped[str] = mapped_column(String(255), nullable=False)  # denormalized for fast reads
    quantity_g: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    calories: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    carbs_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    meal: Mapped = relationship("Meal", back_populates="items")
    food: Mapped = relationship("Food", back_populates="meal_items")


class Supplement(UUIDMixin, TimestampMixin, Base):
    """Supplement log entry."""

    __tablename__ = "supplements"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(255))
    dosage: Mapped[str | None] = mapped_column(String(100))
    timing: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
