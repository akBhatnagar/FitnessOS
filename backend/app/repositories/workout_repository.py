"""
Workout repository — DB operations for WorkoutPlans, Sessions, Exercises, and ExerciseHistory.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workout import (
    WorkoutPlan,
    WorkoutSession,
    Exercise,
    ExerciseHistory,
    WorkoutSet,
    SessionStatus,
)
from app.repositories.base import BaseRepository


class WorkoutRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Plans ──────────────────────────────────────────────────────────────

    async def get_active_plan(self, user_id: UUID) -> WorkoutPlan | None:
        result = await self.db.execute(
            select(WorkoutPlan)
            .where(
                WorkoutPlan.user_id == user_id,
                WorkoutPlan.is_active.is_(True),
            )
            .order_by(desc(WorkoutPlan.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ─── Sessions ──────────────────────────────────────────────────────────

    async def get_today_sessions(self, user_id: UUID) -> Sequence[WorkoutSession]:
        today = date.today()
        result = await self.db.execute(
            select(WorkoutSession)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.scheduled_date == today,
            )
            .order_by(WorkoutSession.scheduled_time)
        )
        return result.scalars().all()

    async def get_sessions_in_range(
        self,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> Sequence[WorkoutSession]:
        result = await self.db.execute(
            select(WorkoutSession)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.scheduled_date >= start_date,
                WorkoutSession.scheduled_date <= end_date,
            )
            .order_by(WorkoutSession.scheduled_date, WorkoutSession.scheduled_time)
        )
        return result.scalars().all()

    async def get_completed_sessions_count(
        self,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(WorkoutSession)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.status == SessionStatus.COMPLETED,
                WorkoutSession.scheduled_date >= start_date,
                WorkoutSession.scheduled_date <= end_date,
            )
        )
        return result.scalar_one() or 0

    async def get_recent_sessions(
        self,
        user_id: UUID,
        limit: int = 10,
    ) -> Sequence[WorkoutSession]:
        result = await self.db.execute(
            select(WorkoutSession)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.status == SessionStatus.COMPLETED,
            )
            .order_by(desc(WorkoutSession.scheduled_date))
            .limit(limit)
        )
        return result.scalars().all()

    # ─── Exercises ─────────────────────────────────────────────────────────

    async def search_exercises(
        self,
        query: str,
        muscle_group: str | None = None,
        limit: int = 20,
    ) -> Sequence[Exercise]:
        stmt = select(Exercise).where(
            Exercise.name.ilike(f"%{query}%")
        )
        if muscle_group:
            stmt = stmt.where(Exercise.primary_muscle == muscle_group)
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_exercise_by_name(self, name: str) -> Exercise | None:
        result = await self.db.execute(
            select(Exercise).where(Exercise.name.ilike(name))
        )
        return result.scalar_one_or_none()

    # ─── Exercise History (for progressive overload) ────────────────────────

    async def get_exercise_history(
        self,
        user_id: UUID,
        exercise_id: UUID,
        limit: int = 10,
    ) -> Sequence[ExerciseHistory]:
        """Get recent performance for a specific exercise to calculate progressive overload."""
        result = await self.db.execute(
            select(ExerciseHistory)
            .where(
                ExerciseHistory.user_id == user_id,
                ExerciseHistory.exercise_id == exercise_id,
            )
            .order_by(desc(ExerciseHistory.performed_on))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_best_set(
        self,
        user_id: UUID,
        exercise_id: UUID,
    ) -> ExerciseHistory | None:
        """Get the personal best (highest estimated 1RM) for an exercise."""
        result = await self.db.execute(
            select(ExerciseHistory)
            .where(
                ExerciseHistory.user_id == user_id,
                ExerciseHistory.exercise_id == exercise_id,
            )
            .order_by(desc(ExerciseHistory.estimated_1rm))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def log_sets(
        self,
        session_id: UUID,
        exercise_id: UUID,
        sets: list[dict],
    ) -> list[WorkoutSet]:
        """
        Persist workout sets for a session.

        Each dict in sets should have: set_number, weight_kg, reps, rpe (optional).
        """
        records = []
        for s in sets:
            ws = WorkoutSet(
                session_id=session_id,
                exercise_id=exercise_id,
                set_number=s["set_number"],
                weight_kg=s.get("weight_kg"),
                reps=s.get("reps"),
                rpe=s.get("rpe"),
                is_completed=s.get("is_completed", True),
            )
            self.db.add(ws)
            records.append(ws)
        await self.db.flush()
        return records
