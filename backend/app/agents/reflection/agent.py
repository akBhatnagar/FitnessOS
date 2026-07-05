"""Reflection Agent — weekly review and continuous improvement."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentState, BaseAgent
from app.db.models.user import User
from app.db.models.workout import WorkoutSession, SessionStatus
from app.db.models.nutrition import Meal
from app.db.models.analytics import WeeklyReview
from app.db.models.measurement import Measurement
from app.db.models.memory import MemoryStore, MemoryType
from app.core.logging import get_logger

logger = get_logger("agent.reflection")


class ReflectionAgent(BaseAgent):
    name = "reflection_agent"
    description = "Weekly coaching reports, pattern recognition, continuous improvement"

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db

    @property
    def system_prompt(self) -> str:
        return """You are an introspective coaching analyst who identifies patterns and drives improvement.

Every Sunday, you review the past 7 days and produce a coaching report that:
1. Celebrates genuine wins (no matter how small)
2. Identifies the #1 bottleneck to progress
3. Proposes specific, actionable improvements for next week
4. Updates the coaching strategy based on what worked and what didn't
5. Predicts next week's expected outcomes

Your tone is honest but encouraging — like a coach who cares deeply about long-term success.
Be specific, never generic. Reference the actual numbers from the data.
"""

    async def process(self, state: AgentState) -> AgentState:
        """Handle reflection-related chat questions inline."""
        if not state.get("needs_reflection_agent"):
            return state

        self._append_trace(state, "Running inline reflection analysis")
        user_id = state.get("user_id", "")
        week_start = date.today() - timedelta(days=7)

        data = await self._gather_week_data(user_id, week_start, date.today())
        report = await self._generate_report(data)

        state["reflection_context"] = {
            "report": report,
            "week_data": data,
        }
        return state

    async def generate_weekly_review(self, user_id: str) -> dict[str, Any]:
        """
        Generate the full weekly coaching report.

        Called by the Celery Sunday review worker and on-demand from chat.
        """
        week_start = date.today() - timedelta(days=7)
        week_end = date.today()

        data = await self._gather_week_data(user_id, week_start, week_end)
        report = await self._generate_report(data)
        insights = await self._extract_coaching_learnings(report, data)

        # Persist insights to memory store
        await self._store_insights(user_id, insights)

        return {
            "report": report,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "week_data": data,
            "insights_stored": len(insights),
        }

    async def _gather_week_data(
        self, user_id: str, week_start: date, week_end: date
    ) -> dict[str, Any]:
        """Gather all measurable data for the past week from the database."""
        # Resolve clerk_user_id → internal UUID
        u = await self.db.execute(
            select(User.id).where(User.clerk_user_id == user_id)
        )
        user_row = u.first()
        if not user_row:
            return {}
        uid = user_row[0]

        # --- Gym sessions ---
        sessions_result = await self.db.execute(
            select(WorkoutSession).where(
                WorkoutSession.user_id == uid,
                WorkoutSession.scheduled_date >= week_start,
                WorkoutSession.scheduled_date <= week_end,
            )
        )
        sessions = sessions_result.scalars().all()
        gym_planned = len(sessions)
        gym_completed = sum(1 for s in sessions if s.status == SessionStatus.COMPLETED)

        # --- Nutrition: average daily calories + protein over week ---
        meals_result = await self.db.execute(
            select(Meal).where(
                Meal.user_id == uid,
                Meal.meal_date >= week_start,
                Meal.meal_date <= week_end,
            )
        )
        meals = meals_result.scalars().all()
        days_with_logs = len({m.meal_date for m in meals}) or 1
        total_cals = sum(float(m.total_calories or 0) for m in meals)
        total_protein = sum(float(m.total_protein_g or 0) for m in meals)
        avg_daily_cals = round(total_cals / days_with_logs)
        avg_daily_protein = round(total_protein / days_with_logs)

        # --- Weight measurements ---
        meas_result = await self.db.execute(
            select(Measurement).where(
                Measurement.user_id == uid,
                Measurement.measurement_date >= week_start,
                Measurement.measurement_date <= week_end,
            ).order_by(Measurement.measurement_date)
        )
        measurements = meas_result.scalars().all()
        weight_start = float(measurements[0].weight_kg) if measurements else None
        weight_end = float(measurements[-1].weight_kg) if measurements else None

        # --- Latest weekly review score (from prior week) ---
        review_result = await self.db.execute(
            select(WeeklyReview).where(
                WeeklyReview.user_id == uid,
                WeeklyReview.week_start_date < week_start,
            ).order_by(WeeklyReview.week_start_date.desc()).limit(1)
        )
        last_review = review_result.scalar_one_or_none()
        last_score = last_review.overall_score if last_review else None

        return {
            "gym_sessions_planned": gym_planned,
            "gym_sessions_completed": gym_completed,
            "gym_adherence_pct": round(gym_completed / gym_planned * 100) if gym_planned else 0,
            "avg_daily_calories": avg_daily_cals,
            "avg_daily_protein": avg_daily_protein,
            "weight_start_kg": weight_start,
            "weight_end_kg": weight_end,
            "weight_change_kg": round(weight_end - weight_start, 2) if weight_start and weight_end else None,
            "days_logged_nutrition": days_with_logs,
            "last_week_score": last_score,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
        }

    async def _generate_report(self, data: dict[str, Any]) -> str:
        """Generate the narrative coaching report via LLM."""
        prompt = f"""Generate a comprehensive weekly coaching report based on this real data:

{json.dumps(data, indent=2)}

USER PROFILE CONTEXT:
- Goal: Fat loss from 100kg → 85kg for wedding (Jan 30, 2027)
- Pre-wedding shoot: Oct 20, 2026
- Diet: Indian vegetarian (eggs OK after evening gym)
- Gym: 9PM, Swimming: 8AM, Work: 10:30AM-8PM

Include in your report:
1. Overall week score (0-100) with clear reasoning tied to actual numbers
2. Top 3 wins (reference specific metrics)
3. Top 3 areas for improvement (specific, actionable)
4. Root cause of the biggest bottleneck
5. Concrete plan adjustments for next week
6. Motivational message that's honest (no toxic positivity — be real)
7. Predicted weight at wedding if current trend continues

Keep it under 400 words. Be a coach, not a cheerleader."""

        response = await self.llm.ainvoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ])
        return response.content

    async def _extract_coaching_learnings(
        self, report: str, data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Extract durable coaching insights from the weekly review for long-term memory."""
        prompt = f"""From this weekly coaching report, extract 3-5 coaching insights to remember long-term.
Focus on patterns, what's working, and what to try differently.

Report: {report}
Data: {json.dumps(data)}

Return ONLY valid JSON:
{{"insights": [{{"category": "adherence|nutrition|training|recovery|psychology", "content": "specific insight text", "importance": 0.8}}]}}"""

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        try:
            cleaned = response.content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            parsed = json.loads(cleaned.strip())
            return parsed.get("insights", [])
        except (json.JSONDecodeError, KeyError, IndexError):
            logger.warning("Failed to parse coaching insights JSON")
            return []

    async def _store_insights(self, user_id: str, insights: list[dict]) -> None:
        """Persist extracted coaching insights to the memory store."""
        u = await self.db.execute(
            select(User.id).where(User.clerk_user_id == user_id)
        )
        user_row = u.first()
        if not user_row:
            return

        uid = user_row[0]
        for insight in insights:
            memory = MemoryStore(
                user_id=uid,
                memory_type=MemoryType.PROCEDURAL,
                category=insight.get("category", "coaching"),
                content=insight.get("content", ""),
                importance_score=insight.get("importance", 0.7),
                source_type="weekly_review",
            )
            self.db.add(memory)

        await self.db.flush()
        logger.info("Stored reflection insights", count=len(insights))
