"""Coach note model — AI-generated coaching observations."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class CoachNote(UUIDMixin, TimestampMixin, Base):
    """
    Coaching observation written by an AI agent.

    Used by the Reflection Agent to accumulate coaching wisdom over time.
    These notes feed back into the Memory Agent's long-term storage.
    """

    __tablename__ = "coach_notes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    note_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    agent_source: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    action_items: Mapped[list] = mapped_column(ARRAY(String), default=list)
    is_shared_with_user: Mapped[bool] = mapped_column()

    user: Mapped = relationship("User", back_populates="coach_notes")
