"""
Nutrition Agent — tracks macros and provides personalised dietary guidance.

This agent:
1. Loads today's meal data and macro totals from DB
2. Checks against user's protein and calorie targets
3. Builds nutrition context for the Coach Agent
4. Can suggest specific foods from the Indian vegetarian food database
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentState, BaseAgent
from app.db.models.user import User, UserPreferences
from app.db.models.nutrition import Food, Meal, MealItem
from app.repositories.nutrition_repository import NutritionRepository
from app.core.logging import get_logger

logger = get_logger("agent.nutrition")


class NutritionAgent(BaseAgent):
    name = "nutrition_agent"
    description = "Tracks macros, suggests Indian vegetarian meals, optimises protein intake"

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db
        self.repo = NutritionRepository(db)

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Nutrition Specialist for FitnessOS. "
            "You focus on Indian vegetarian nutrition for fat loss and muscle building. "
            "You know the user's food preferences: allowed (paneer, whey, curd, milk, eggs after gym), "
            "disallowed (tofu, soya chunks, creatine). "
            "Always give specific quantities in grams and calories."
        )

    async def process(self, state: AgentState) -> AgentState:
        """Load nutrition context from DB."""
        user_id_str = state.get("user_id", "")
        self._append_trace(state, "Loading nutrition context from DB")

        try:
            result = await self.db.execute(
                select(User, UserPreferences)
                .outerjoin(UserPreferences, User.id == UserPreferences.user_id)
                .where(User.clerk_user_id == user_id_str)
            )
            row = result.first()
            if not row:
                state["nutrition_context"] = "No user found."
                return state

            user, prefs = row.User, row.UserPreferences
            today = date.today()

            # Today's macro totals
            today_macros = await self.repo.get_daily_macro_totals(user.id, today)

            # Today's meals
            today_meals = await self.repo.get_meals_on_date(user.id, today)

            # Calculate targets
            weight = float(prefs.current_weight_kg) if prefs and prefs.current_weight_kg else 100.0
            target_protein = round(weight * 1.7)
            target_calories = round(weight * 22)

            # Get high-protein food suggestions if needed
            protein_remaining = target_protein - today_macros["protein_g"]
            high_protein_foods = []
            if protein_remaining > 30:
                high_protein_foods = await self.repo.get_high_protein_foods(
                    min_protein_per_100g=10.0,
                    vegetarian_only=True,
                    limit=5,
                )

            context = self._format_nutrition_context(
                today_macros, today_meals, target_protein, target_calories, protein_remaining, high_protein_foods
            )
            state["nutrition_context"] = context
            self._append_trace(state, f"Nutrition context loaded — {len(today_meals)} meals, {round(today_macros['protein_g'])}g protein")

        except Exception as e:
            logger.error("Nutrition agent failed", error=str(e))
            state["nutrition_context"] = f"Nutrition data temporarily unavailable: {e}"

        return state

    def _format_nutrition_context(
        self,
        macros: dict,
        meals: list,
        target_protein: float,
        target_calories: float,
        protein_remaining: float,
        high_protein_foods: list,
    ) -> str:
        lines = [
            f"TODAY'S NUTRITION:",
            f"  Calories: {round(macros['calories'])} / {round(target_calories)} kcal",
            f"  Protein:  {round(macros['protein_g'])}g / {round(target_protein)}g",
            f"  Carbs:    {round(macros['carbs_g'])}g",
            f"  Fat:      {round(macros['fat_g'])}g",
            f"  Meals logged: {len(meals)}",
        ]

        if protein_remaining > 0:
            lines.append(f"\n  ⚠ {round(protein_remaining)}g protein still needed today")
            if high_protein_foods:
                lines.append("  Best options to hit target:")
                for food in high_protein_foods[:3]:
                    lines.append(
                        f"    - {food.name}: {food.protein_g}g protein / 100g "
                        f"({round(float(food.calories_per_100g))} kcal)"
                    )
        else:
            lines.append(f"\n  ✓ Protein target achieved!")

        if meals:
            lines.append(f"\nMeals today:")
            for m in meals:
                lines.append(
                    f"  - {m.meal_type}: {round(float(m.total_calories or 0))} kcal, "
                    f"{round(float(m.total_protein_g or 0))}g P"
                )

        return "\n".join(lines)
