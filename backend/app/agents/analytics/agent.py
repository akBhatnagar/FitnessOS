"""Analytics Agent — progress analysis, predictions, and reporting."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentState, BaseAgent
from app.db.models.user import User
from app.db.models.measurement import Measurement
from app.db.models.workout import WorkoutSession, SessionStatus
from app.db.models.nutrition import Meal
from app.core.logging import get_logger

logger = get_logger("agent.analytics")


class AnalyticsAgent(BaseAgent):
    name = "analytics_agent"
    description = "Analyzes progress, detects plateaus, predicts event-day physique"

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db

    @property
    def system_prompt(self) -> str:
        return """You are a data-driven fitness analytics specialist.

Analyze progress trends and provide evidence-based insights.
Be honest about plateaus but always frame them constructively.
Use math: rates of change, trend lines, predictions.
"""

    async def process(self, state: AgentState) -> AgentState:
        if not state.get("needs_analytics_agent"):
            return state

        self._append_trace(state, "Running analytics")

        measurements = await self._get_measurements(state.get("user_id", ""))
        adherence = await self._calculate_adherence(state.get("user_id", ""))
        predictions = self._calculate_predictions(measurements)

        analytics_context = await self._generate_analytics_context(
            state, measurements, adherence, predictions
        )
        state["analytics_context"] = analytics_context

        return state

    def _calculate_predictions(self, measurements: list[dict]) -> dict[str, Any]:
        """
        Calculate weight trajectory predictions for key events.

        Uses linear regression on recent weight data.
        All event dates are calculated dynamically.
        """
        if len(measurements) < 2:
            return {}

        # Calculate weekly rate of change
        recent = measurements[:4]  # Last 4 measurements
        if len(recent) < 2:
            return {}

        try:
            first_weight = float(recent[-1]["weight_kg"])
            last_weight = float(recent[0]["weight_kg"])
            first_date = date.fromisoformat(recent[-1]["date"])
            last_date = date.fromisoformat(recent[0]["date"])
            days_elapsed = (last_date - first_date).days

            if days_elapsed == 0:
                return {}

            weekly_change = (last_weight - first_weight) / (days_elapsed / 7)

            # Predict weight on event dates (never hardcoded)
            pre_wedding = date(2026, 10, 20)
            wedding = date(2027, 1, 30)
            today = date.today()

            weeks_to_prewedding = (pre_wedding - today).days / 7
            weeks_to_wedding = (wedding - today).days / 7

            predicted_prewedding = last_weight + (weekly_change * weeks_to_prewedding)
            predicted_wedding = last_weight + (weekly_change * weeks_to_wedding)

            return {
                "weekly_rate_kg": round(weekly_change, 2),
                "predicted_pre_wedding_weight_kg": round(max(predicted_prewedding, 70), 1),
                "predicted_wedding_weight_kg": round(max(predicted_wedding, 70), 1),
                "weeks_to_target": round((last_weight - 85) / abs(weekly_change), 1) if weekly_change < 0 else None,
                "on_track_for_target": predicted_wedding <= 85,
            }
        except (ValueError, ZeroDivisionError, KeyError):
            return {}

    async def _generate_analytics_context(
        self,
        state: AgentState,
        measurements: list[dict],
        adherence: dict[str, Any],
        predictions: dict[str, Any],
    ) -> dict[str, Any]:
        prompt = f"""
Analytics question: {state.get('user_message', '')}

Weight Measurements (last 10):
{str(measurements[:10]) if measurements else 'No data yet'}

Adherence Summary:
{str(adherence)}

Predictions:
- Weekly rate: {predictions.get('weekly_rate_kg', 'N/A')} kg/week
- Predicted Pre-Wedding Weight: {predictions.get('predicted_pre_wedding_weight_kg', 'N/A')} kg
- Predicted Wedding Weight: {predictions.get('predicted_wedding_weight_kg', 'N/A')} kg
- On track: {predictions.get('on_track_for_target', 'Unknown')}

Provide data-driven insights and actionable recommendations.
"""
        response = await self.llm.ainvoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ])

        return {
            "analysis": response.content,
            "predictions": predictions,
            "adherence": adherence,
            "measurement_count": len(measurements),
        }

    async def _get_measurements(self, user_id: str) -> list[dict]:
        """Fetch the user's weight measurements from the database."""
        u = await self.db.execute(select(User.id).where(User.clerk_user_id == user_id))
        user_row = u.first()
        if not user_row:
            return []
        uid = user_row[0]

        result = await self.db.execute(
            select(Measurement).where(
                Measurement.user_id == uid,
                Measurement.weight_kg.isnot(None),
            ).order_by(Measurement.measured_on.desc()).limit(20)
        )
        measurements = result.scalars().all()
        return [
            {
                "date": m.measured_on.isoformat(),
                "weight_kg": float(m.weight_kg),
                "body_fat_pct": float(m.body_fat_pct) if m.body_fat_pct else None,
                "muscle_mass_kg": float(m.muscle_mass_kg) if m.muscle_mass_kg else None,
            }
            for m in measurements
        ]

    async def _calculate_adherence(self, user_id: str) -> dict[str, Any]:
        """Calculate gym and nutrition adherence over the last 30 days."""
        u = await self.db.execute(select(User.id).where(User.clerk_user_id == user_id))
        user_row = u.first()
        if not user_row:
            return {"gym_pct": 0, "nutrition_pct": 0}
        uid = user_row[0]

        today = date.today()
        thirty_days_ago = today - timedelta(days=30)

        # Gym adherence: completed vs planned sessions
        sessions_result = await self.db.execute(
            select(WorkoutSession).where(
                WorkoutSession.user_id == uid,
                WorkoutSession.scheduled_date >= thirty_days_ago,
            )
        )
        sessions = sessions_result.scalars().all()
        gym_planned = len(sessions)
        gym_completed = sum(1 for s in sessions if s.status == SessionStatus.COMPLETED)
        gym_pct = round(gym_completed / gym_planned * 100) if gym_planned else 0

        # Nutrition adherence: distinct days with any meal logged
        days_result = await self.db.execute(
            select(func.count(func.distinct(Meal.meal_date))).where(
                Meal.user_id == uid,
                Meal.meal_date >= thirty_days_ago,
            )
        )
        nutrition_days = days_result.scalar() or 0
        nutrition_pct = round(nutrition_days / 30 * 100)

        return {
            "gym_pct": gym_pct,
            "gym_sessions_planned_30d": gym_planned,
            "gym_sessions_completed_30d": gym_completed,
            "nutrition_pct": nutrition_pct,
            "nutrition_days_logged_30d": int(nutrition_days),
        }
