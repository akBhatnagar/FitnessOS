"""
User repository — all DB operations for User, UserPreferences, and Goals.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.user import User, UserPreferences
from app.db.models.goal import Goal
from app.db.models.event import Event
from app.db.models.measurement import Measurement
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(User, db)

    async def get_by_clerk_id(self, clerk_id: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.clerk_user_id == clerk_id)
        )
        return result.scalar_one_or_none()

    async def get_with_preferences(self, clerk_id: str) -> tuple[User, UserPreferences | None] | None:
        result = await self.db.execute(
            select(User, UserPreferences)
            .outerjoin(UserPreferences, User.id == UserPreferences.user_id)
            .where(User.clerk_user_id == clerk_id)
        )
        row = result.first()
        if not row:
            return None
        return row.User, row.UserPreferences

    async def get_active_goals(self, user_id: UUID) -> Sequence[Goal]:
        result = await self.db.execute(
            select(Goal)
            .where(Goal.user_id == user_id, Goal.status == "active")
            .order_by(Goal.priority)
        )
        return result.scalars().all()

    async def get_upcoming_events(self, user_id: UUID, limit: int = 5) -> Sequence[Event]:
        today = date.today()
        result = await self.db.execute(
            select(Event)
            .where(
                Event.user_id == user_id,
                Event.is_active.is_(True),
                Event.event_date >= today,
            )
            .order_by(Event.event_date)
            .limit(limit)
        )
        return result.scalars().all()

    async def get_latest_measurement(self, user_id: UUID) -> Measurement | None:
        result = await self.db.execute(
            select(Measurement)
            .where(Measurement.user_id == user_id)
            .order_by(Measurement.measured_on.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_weight_history(self, user_id: UUID, weeks: int = 12) -> Sequence[Measurement]:
        result = await self.db.execute(
            select(Measurement)
            .where(Measurement.user_id == user_id)
            .order_by(Measurement.measured_on.desc())
            .limit(weeks)
        )
        rows = result.scalars().all()
        return list(reversed(rows))
