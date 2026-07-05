"""
SQLAlchemy declarative base and shared mixin classes.

All models inherit from Base. The TimestampMixin and UUIDMixin are applied
to every table automatically to ensure audit trails and stable identifiers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedColumn, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all FitnessOS models."""

    # Allow untyped relationship() calls alongside Mapped[] annotations.
    # This avoids the need to type every back-reference with full generics.
    __allow_unmapped__ = True


class UUIDMixin:
    """Provides a UUID primary key. All FitnessOS tables use UUIDs."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )


class TimestampMixin:
    """Provides created_at and updated_at audit columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """
    Provides soft delete support.

    Rows with deleted_at set are excluded from normal queries via
    a repository-level filter — they are never physically removed.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
