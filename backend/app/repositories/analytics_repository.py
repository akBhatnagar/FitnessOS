"""
Analytics repository — DB operations for WeeklyReviews, MonthlyReports, Predictions, Achievements.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.analytics import WeeklyReview, MonthlyReport, Prediction, Achievement
from app.repositories.base import BaseRepository


class AnalyticsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Weekly Reviews ─────────────────────────────────────────────────────

    async def get_latest_weekly_review(self, user_id: UUID) -> WeeklyReview | None:
        result = await self.db.execute(
            select(WeeklyReview)
            .where(WeeklyReview.user_id == user_id)
            .order_by(desc(WeeklyReview.week_start))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_weekly_reviews(
        self,
        user_id: UUID,
        limit: int = 8,
    ) -> Sequence[WeeklyReview]:
        result = await self.db.execute(
            select(WeeklyReview)
            .where(WeeklyReview.user_id == user_id)
            .order_by(desc(WeeklyReview.week_start))
            .limit(limit)
        )
        return result.scalars().all()

    async def save_weekly_review(
        self,
        user_id: UUID,
        week_start: date,
        week_end: date,
        **kwargs,
    ) -> WeeklyReview:
        review = WeeklyReview(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            **kwargs,
        )
        self.db.add(review)
        await self.db.flush()
        return review

    # ─── Predictions ────────────────────────────────────────────────────────

    async def get_latest_prediction(
        self,
        user_id: UUID,
        prediction_type: str,
    ) -> Prediction | None:
        result = await self.db.execute(
            select(Prediction)
            .where(
                Prediction.user_id == user_id,
                Prediction.prediction_type == prediction_type,
            )
            .order_by(desc(Prediction.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save_prediction(
        self,
        user_id: UUID,
        prediction_type: str,
        predicted_value: float,
        target_date: date,
        confidence_pct: float,
        methodology: str,
        extra: dict | None = None,
    ) -> Prediction:
        pred = Prediction(
            user_id=user_id,
            prediction_type=prediction_type,
            predicted_value=predicted_value,
            target_date=target_date,
            confidence_pct=confidence_pct,
            methodology=methodology,
            extra=extra or {},
        )
        self.db.add(pred)
        await self.db.flush()
        return pred

    # ─── Achievements ───────────────────────────────────────────────────────

    async def get_recent_achievements(
        self,
        user_id: UUID,
        limit: int = 5,
    ) -> Sequence[Achievement]:
        result = await self.db.execute(
            select(Achievement)
            .where(Achievement.user_id == user_id)
            .order_by(desc(Achievement.achieved_on))
            .limit(limit)
        )
        return result.scalars().all()

    async def award_achievement(
        self,
        user_id: UUID,
        title: str,
        description: str,
        achievement_type: str,
        icon: str = "trophy",
        points: int = 10,
    ) -> Achievement:
        achievement = Achievement(
            user_id=user_id,
            title=title,
            description=description,
            achievement_type=achievement_type,
            icon=icon,
            points=points,
            achieved_on=date.today(),
        )
        self.db.add(achievement)
        await self.db.flush()
        return achievement
