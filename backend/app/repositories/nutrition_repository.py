"""
Nutrition repository — DB operations for NutritionPlans, Meals, MealItems, FoodDatabase.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.nutrition import (
    NutritionPlan,
    Meal,
    MealItem,
    Food as FoodItem,
)
from app.repositories.base import BaseRepository


class NutritionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Nutrition Plans ────────────────────────────────────────────────────

    async def get_active_plan(self, user_id: UUID) -> NutritionPlan | None:
        result = await self.db.execute(
            select(NutritionPlan)
            .where(
                NutritionPlan.user_id == user_id,
                NutritionPlan.is_active.is_(True),
            )
            .order_by(desc(NutritionPlan.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ─── Meals ──────────────────────────────────────────────────────────────

    async def get_meals_on_date(self, user_id: UUID, on_date: date) -> Sequence[Meal]:
        result = await self.db.execute(
            select(Meal)
            .where(
                Meal.user_id == user_id,
                Meal.meal_date == on_date,
            )
            .order_by(Meal.meal_time)
        )
        return result.scalars().all()

    async def get_meals_in_range(
        self,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> Sequence[Meal]:
        result = await self.db.execute(
            select(Meal)
            .where(
                Meal.user_id == user_id,
                Meal.meal_date >= start_date,
                Meal.meal_date <= end_date,
            )
            .order_by(Meal.meal_date, Meal.meal_time)
        )
        return result.scalars().all()

    async def get_daily_macro_totals(
        self,
        user_id: UUID,
        on_date: date,
    ) -> dict:
        """Aggregate calories, protein, carbs, fat for a given day."""
        result = await self.db.execute(
            select(
                func.coalesce(func.sum(Meal.total_calories), 0).label("calories"),
                func.coalesce(func.sum(Meal.total_protein_g), 0).label("protein_g"),
                func.coalesce(func.sum(Meal.total_carbs_g), 0).label("carbs_g"),
                func.coalesce(func.sum(Meal.total_fat_g), 0).label("fat_g"),
            )
            .where(
                Meal.user_id == user_id,
                Meal.meal_date == on_date,
            )
        )
        row = result.one()
        return {
            "calories": float(row.calories),
            "protein_g": float(row.protein_g),
            "carbs_g": float(row.carbs_g),
            "fat_g": float(row.fat_g),
        }

    async def get_weekly_avg_macros(
        self,
        user_id: UUID,
        week_start: date,
        week_end: date,
    ) -> dict:
        result = await self.db.execute(
            select(
                func.coalesce(func.avg(Meal.total_calories), 0).label("avg_calories"),
                func.coalesce(func.avg(Meal.total_protein_g), 0).label("avg_protein_g"),
                func.coalesce(func.avg(Meal.total_carbs_g), 0).label("avg_carbs_g"),
                func.coalesce(func.avg(Meal.total_fat_g), 0).label("avg_fat_g"),
            )
            .where(
                Meal.user_id == user_id,
                Meal.meal_date >= week_start,
                Meal.meal_date <= week_end,
            )
        )
        row = result.one()
        return {
            "avg_calories": float(row.avg_calories),
            "avg_protein_g": float(row.avg_protein_g),
            "avg_carbs_g": float(row.avg_carbs_g),
            "avg_fat_g": float(row.avg_fat_g),
        }

    # ─── Food Database ──────────────────────────────────────────────────────

    async def search_food(
        self,
        query: str,
        vegetarian_only: bool = True,
        limit: int = 20,
    ) -> Sequence[FoodItem]:
        stmt = select(FoodItem).where(FoodItem.name.ilike(f"%{query}%"))
        if vegetarian_only:
            stmt = stmt.where(FoodItem.is_vegetarian.is_(True))
        stmt = stmt.order_by(FoodItem.name).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_food_by_name(self, name: str) -> FoodItem | None:
        result = await self.db.execute(
            select(FoodItem).where(FoodItem.name.ilike(name)).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_high_protein_foods(
        self,
        min_protein_per_100g: float = 15.0,
        vegetarian_only: bool = True,
        limit: int = 30,
    ) -> Sequence[FoodItem]:
        """Returns vegetarian high-protein foods, sorted by protein density."""
        stmt = select(FoodItem).where(
            FoodItem.protein_g >= min_protein_per_100g
        )
        if vegetarian_only:
            stmt = stmt.where(FoodItem.is_vegetarian.is_(True))
        stmt = stmt.order_by(desc(FoodItem.protein_g)).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_foods_by_tag(
        self,
        tag: str,
        vegetarian_only: bool = True,
        limit: int = 50,
    ) -> Sequence[FoodItem]:
        """Filter foods by tag (e.g., 'dairy', 'legume', 'grain', 'street_food')."""
        stmt = select(FoodItem).where(FoodItem.tags.any(tag))
        if vegetarian_only:
            stmt = stmt.where(FoodItem.is_vegetarian.is_(True))
        stmt = stmt.order_by(FoodItem.name).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()
