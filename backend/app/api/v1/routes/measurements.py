"""Measurements and progress tracking API."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenPayload, get_current_user
from app.db.models.measurement import Measurement
from app.db.models.user import User, UserPreferences
from app.db.session import get_db

router = APIRouter(prefix="/measurements", tags=["Measurements"])


class MeasurementCreateRequest(BaseModel):
    measured_on: date
    weight_kg: float | None = Field(None, gt=0, lt=500)
    body_fat_pct: float | None = Field(None, ge=0, le=100)
    waist_cm: float | None = None
    chest_cm: float | None = None
    hips_cm: float | None = None
    shoulders_cm: float | None = None
    left_bicep_cm: float | None = None
    right_bicep_cm: float | None = None
    energy_level: int | None = Field(None, ge=1, le=10)
    sleep_quality: int | None = Field(None, ge=1, le=10)
    stress_level: int | None = Field(None, ge=1, le=10)
    pain_level: int | None = Field(None, ge=0, le=10)
    pain_location: str | None = None
    notes: str | None = None


class MeasurementResponse(BaseModel):
    id: str
    measured_on: str
    weight_kg: float | None
    body_fat_pct: float | None
    waist_cm: float | None
    energy_level: int | None
    sleep_quality: int | None


@router.post("/", status_code=201)
async def log_measurement(
    request: MeasurementCreateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Log a body measurement snapshot."""
    result = await db.execute(
        select(User).where(User.clerk_user_id == current_user.sub)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if request.measured_on > date.today():
        raise HTTPException(status_code=400, detail="Cannot log measurements for future dates")

    existing_result = await db.execute(
        select(Measurement).where(
            Measurement.user_id == user.id,
            Measurement.measured_on == request.measured_on,
        )
    )
    measurement = existing_result.scalar_one_or_none()

    if measurement:
        for field, value in request.model_dump(exclude_none=True).items():
            if field != "measured_on":
                setattr(measurement, field, value)
    else:
        measurement = Measurement(
            user_id=user.id,
            **request.model_dump(exclude_none=True),
        )
        db.add(measurement)

    if request.weight_kg and request.measured_on == date.today():
        prefs_result = await db.execute(
            select(UserPreferences).where(UserPreferences.user_id == user.id)
        )
        prefs = prefs_result.scalar_one_or_none()
        if prefs:
            prefs.current_weight_kg = Decimal(str(request.weight_kg))

    await db.flush()
    await db.commit()

    return {"status": "logged", "id": str(measurement.id)}


@router.get("/", response_model=list[MeasurementResponse])
async def get_measurements(
    limit: int = 30,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MeasurementResponse]:
    """Get measurement history, most recent first."""
    result = await db.execute(
        select(User).where(User.clerk_user_id == current_user.sub)
    )
    user = result.scalar_one_or_none()
    if not user:
        return []

    m_result = await db.execute(
        select(Measurement)
        .where(Measurement.user_id == user.id)
        .order_by(Measurement.measured_on.desc())
        .limit(limit)
    )
    measurements = m_result.scalars().all()

    return [
        MeasurementResponse(
            id=str(m.id),
            measured_on=m.measured_on.isoformat(),
            weight_kg=float(m.weight_kg) if m.weight_kg else None,
            body_fat_pct=float(m.body_fat_pct) if m.body_fat_pct else None,
            waist_cm=float(m.waist_cm) if m.waist_cm else None,
            energy_level=m.energy_level,
            sleep_quality=m.sleep_quality,
        )
        for m in measurements
    ]


@router.get("/latest")
async def get_latest_measurement(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MeasurementResponse | None:
    """Get the most recent measurement."""
    result = await db.execute(
        select(User).where(User.clerk_user_id == current_user.sub)
    )
    user = result.scalar_one_or_none()
    if not user:
        return None

    m_result = await db.execute(
        select(Measurement)
        .where(Measurement.user_id == user.id)
        .order_by(Measurement.measured_on.desc())
        .limit(1)
    )
    m = m_result.scalar_one_or_none()
    if not m:
        return None

    return MeasurementResponse(
        id=str(m.id),
        measured_on=m.measured_on.isoformat(),
        weight_kg=float(m.weight_kg) if m.weight_kg else None,
        body_fat_pct=float(m.body_fat_pct) if m.body_fat_pct else None,
        waist_cm=float(m.waist_cm) if m.waist_cm else None,
        energy_level=m.energy_level,
        sleep_quality=m.sleep_quality,
    )
