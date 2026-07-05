"""
Workout Agent — creates workout programs and tracks progressive overload.

This agent:
1. Loads the user's active workout plan from DB
2. Checks recent session history and exercise performance
3. Calculates progressive overload recommendations using the Epley engine
4. Updates state["workout_context"] for the Coach Agent to use
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentState, BaseAgent
from app.db.models.user import User
from app.db.models.workout import Exercise, SessionStatus, WorkoutPlan, WorkoutSession, WorkoutSet
from app.repositories.workout_repository import WorkoutRepository
from app.services.training.progressive_overload import (
    ExercisePerformance,
    ProgressionStrategy,
    SetRecord,
    calculate_progression,
    estimate_1rm,
)
from app.core.logging import get_logger

logger = get_logger("agent.workout")


class WorkoutAgent(BaseAgent):
    name = "workout_agent"
    description = "Creates programs, tracks progression, and calculates progressive overload"

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db
        self.repo = WorkoutRepository(db)

    @property
    def system_prompt(self) -> str:
        return (
            "You are the Workout Specialist for FitnessOS. "
            "You design evidence-based training programs for fat loss with muscle retention. "
            "Your recommendations always use specific weights, sets, and reps."
        )

    async def process(self, state: AgentState) -> AgentState:
        """Load workout context from DB and build progressive overload recommendations."""
        user_id_str = state.get("user_id", "")
        self._append_trace(state, "Loading workout context from DB")

        try:
            # Resolve user UUID
            result = await self.db.execute(
                select(User).where(User.clerk_user_id == user_id_str)
            )
            user = result.scalar_one_or_none()
            if not user:
                state["workout_context"] = "No user found."
                return state

            # Get active plan
            plan = await self.repo.get_active_plan(user.id)

            # Get today's sessions
            today_sessions = await self.repo.get_today_sessions(user.id)

            # Get recent completed sessions (last 5)
            recent_sessions = await self.repo.get_recent_sessions(user.id, limit=5)

            # Build progressive overload suggestions for today's key exercises
            overload_suggestions = await self._build_overload_suggestions(user.id, today_sessions)

            # Calculate weekly adherence
            from datetime import timedelta
            week_start = date.today() - timedelta(days=date.today().weekday())
            week_end = date.today()
            completed_this_week = await self.repo.get_completed_sessions_count(
                user.id, week_start, week_end
            )

            context = self._format_workout_context(
                plan, today_sessions, recent_sessions, overload_suggestions, completed_this_week
            )
            state["workout_context"] = context
            self._append_trace(state, f"Workout context loaded — {len(today_sessions)} session(s) today")

        except Exception as e:
            logger.error("Workout agent failed", error=str(e))
            state["workout_context"] = f"Workout data temporarily unavailable: {e}"

        return state

    async def _build_overload_suggestions(
        self,
        user_id,
        today_sessions: list,
    ) -> list[dict]:
        """Build progressive overload suggestions for exercises in today's sessions."""
        suggestions = []
        if not today_sessions:
            return suggestions

        # Get sets from today's sessions to find exercises
        for session in today_sessions[:2]:  # limit to first 2 sessions
            sets_result = await self.db.execute(
                select(WorkoutSet, Exercise.name, Exercise.is_compound)
                .join(Exercise, WorkoutSet.exercise_id == Exercise.id)
                .where(WorkoutSet.session_id == session.id)
                .limit(10)
            )
            session_exercises = sets_result.fetchall()

            for row in session_exercises[:3]:  # top 3 exercises per session
                exercise_id = row.WorkoutSet.exercise_id

                # Get last 5 sets for this exercise
                history_result = await self.db.execute(
                    select(WorkoutSet, WorkoutSession.scheduled_date)
                    .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
                    .where(
                        WorkoutSet.exercise_id == exercise_id,
                        WorkoutSession.user_id == user_id,
                        WorkoutSession.status == SessionStatus.COMPLETED,
                        WorkoutSet.actual_weight_kg.isnot(None),
                        WorkoutSet.actual_reps.isnot(None),
                    )
                    .order_by(desc(WorkoutSession.scheduled_date))
                    .limit(10)
                )
                history = history_result.fetchall()

                if not history:
                    suggestions.append({
                        "exercise": row.name,
                        "recommendation": "No history — start at 20kg and focus on form",
                        "suggested_weight": 20.0,
                    })
                    continue

                set_records = [
                    SetRecord(
                        weight_kg=float(h.WorkoutSet.actual_weight_kg),
                        reps=h.WorkoutSet.actual_reps,
                        rpe=float(h.WorkoutSet.rpe) if h.WorkoutSet.rpe else None,
                        is_top_set=h.WorkoutSet.set_number == 1,
                    )
                    for h in history
                ]

                perf = ExercisePerformance(
                    exercise_name=row.name,
                    sets=set_records,
                    target_reps_min=6 if row.is_compound else 8,
                    target_reps_max=10 if row.is_compound else 15,
                    strategy=ProgressionStrategy.DOUBLE_PROGRESSION,
                )
                rec = calculate_progression(perf)

                suggestions.append({
                    "exercise": row.name,
                    "suggested_weight": rec.recommended_weight_kg,
                    "recommended_reps": f"{rec.recommended_reps_min}-{rec.recommended_reps_max}",
                    "estimated_1rm": rec.estimated_1rm_kg,
                    "rationale": rec.rationale,
                    "deload": rec.deload_recommended,
                })

        return suggestions

    def _format_workout_context(
        self,
        plan,
        today_sessions: list,
        recent_sessions: list,
        suggestions: list[dict],
        completed_this_week: int,
    ) -> str:
        lines = []

        if plan:
            lines.append(f"Active Plan: {plan.session_name if hasattr(plan, 'session_name') else 'Push/Pull/Legs'}")

        lines.append(f"Gym sessions completed this week: {completed_this_week}")

        if today_sessions:
            lines.append(f"\nToday's sessions ({len(today_sessions)}):")
            for s in today_sessions:
                lines.append(f"  - {s.session_name} [{s.status}] — {', '.join(s.muscle_groups_targeted[:3])}")

        if recent_sessions:
            lines.append(f"\nLast {len(recent_sessions)} sessions:")
            for s in recent_sessions:
                lines.append(f"  - {s.scheduled_date.strftime('%b %d')}: {s.session_name}")

        if suggestions:
            lines.append("\nProgressive Overload Suggestions for today:")
            for s in suggestions:
                if "rationale" in s:
                    lines.append(f"  - {s['exercise']}: {s['suggested_weight']}kg × {s['recommended_reps']} — {s['rationale']}")
                else:
                    lines.append(f"  - {s['exercise']}: {s['recommendation']}")

        return "\n".join(lines)
