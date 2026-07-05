"""Body measurement and progress photo models."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Measurement(UUIDMixin, TimestampMixin, Base):
    """
    Body composition snapshot on a given date.

    All measurements are optional — record what was measured each time.
    The Analytics Agent uses this series to compute trends and predictions.
    """

    __tablename__ = "measurements"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    measured_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Weight & composition
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    body_fat_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    muscle_mass_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    water_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))

    # Circumference measurements (cm)
    waist_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    chest_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    hips_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    shoulders_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    left_bicep_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    right_bicep_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    left_thigh_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    right_thigh_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    neck_cm: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))

    # Subjective health indicators
    energy_level: Mapped[int | None] = mapped_column()  # 1-10
    sleep_quality: Mapped[int | None] = mapped_column()  # 1-10
    stress_level: Mapped[int | None] = mapped_column()  # 1-10
    pain_level: Mapped[int | None] = mapped_column()  # 0-10
    pain_location: Mapped[str | None] = mapped_column(String(255))

    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped = relationship("User", back_populates="measurements")

    def __repr__(self) -> str:
        return f"<Measurement {self.measured_on} weight={self.weight_kg}kg>"


class ProgressPhoto(UUIDMixin, TimestampMixin, Base):
    """
    Progress photo with AI-generated analysis.

    Photos are stored in Supabase Storage — only the URL is persisted here.
    The Analytics Agent performs body composition estimation from photos.
    """

    __tablename__ = "progress_photos"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    taken_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    photo_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    photo_angle: Mapped[str] = mapped_column(
        String(50), default="front"
    )  # front, side, back

    # AI analysis results
    ai_analysis: Mapped[dict] = mapped_column(JSONB, default=dict)
    estimated_body_fat_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    visible_improvements: Mapped[list] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<ProgressPhoto {self.taken_on} angle={self.photo_angle}>"
