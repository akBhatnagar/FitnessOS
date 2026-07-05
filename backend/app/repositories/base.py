"""
Base repository providing generic CRUD operations.

All domain repositories inherit from this class to get consistent
create/read/update/delete without duplicating boilerplate.
"""

from __future__ import annotations

from typing import Any, Generic, Sequence, Type, TypeVar
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic async repository for SQLAlchemy models."""

    def __init__(self, model: Type[ModelT], db: AsyncSession) -> None:
        self.model = model
        self.db = db

    async def get_by_id(self, record_id: UUID) -> ModelT | None:
        result = await self.db.execute(
            select(self.model).where(self.model.id == record_id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        result = await self.db.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def create(self, **kwargs: Any) -> ModelT:
        instance = self.model(**kwargs)
        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def update_by_id(self, record_id: UUID, **kwargs: Any) -> ModelT | None:
        await self.db.execute(
            update(self.model)
            .where(self.model.id == record_id)
            .values(**kwargs)
        )
        return await self.get_by_id(record_id)

    async def delete_by_id(self, record_id: UUID) -> bool:
        instance = await self.get_by_id(record_id)
        if not instance:
            return False
        await self.db.delete(instance)
        return True
