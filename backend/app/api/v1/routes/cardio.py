"""
Cardio Log API — log and retrieve post-workout (or standalone) cardio sessions.

Endpoints:
  POST   /cardio          — log a cardio session
  GET    /cardio          — list recent cardio logs (last 30 days)
  GET    /cardio/today    — today's cardio log(s)
  PATCH  /cardio/{id}     — update a cardio log
  DELETE /cardio/{id}     — delete a cardio log
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import today_in_timezone
from app.core.logging import get_logger
from app.core.security import TokenPayload, get_current_user
from app.db.models.user import User
from app.db.models.workout import CardioLog, CardioIntensity, CardioType
from app.db.session import get_db

router = APIRouter(prefix="/cardio", tags=["Cardio"])
logger = get_logger("api.cardio")


# ─── Request / Response Models ───────────────────────────────────────────────


class CardioLogRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="Linked workout session (optional)")
    log_date: Optional[date] = None
    cardio_type: CardioType = CardioType.OTHER
    performed: bool = True
    duration_minutes: Optional[int] = Field(None, ge=1, le=600)
    calories_burned: Optional[int] = Field(None, ge=0, le=10000)
    distance_km: Optional[float] = Field(None, ge=0, le=1000)
    avg_heart_rate: Optional[int] = Field(None, ge=30, le=250)
    intensity: Optional[CardioIntensity] = None
    notes: Optional[str] = Field(None, max_length=1000)


class CardioLogResponse(BaseModel):
    id: str
    session_id: Optional[str]
    log_date: str
    cardio_type: str
    performed: bool
    duration_minutes: Optional[int]
    calories_burned: Optional[int]
    distance_km: Optional[float]
    avg_heart_rate: Optional[int]
    intensity: Optional[str]
    notes: Optional[str]
    created_at: str


def _to_dict(log: CardioLog) -> dict:
    return {
        "id": str(log.id),
        "session_id": str(log.session_id) if log.session_id else None,
        "log_date": log.log_date.isoformat(),
        "cardio_type": log.cardio_type,
        "performed": log.performed,
        "duration_minutes": log.duration_minutes,
        "calories_burned": log.calories_burned,
        "distance_km": float(log.distance_km) if log.distance_km else None,
        "avg_heart_rate": log.avg_heart_rate,
        "intensity": log.intensity,
        "notes": log.notes,
        "created_at": log.created_at.isoformat(),
    }


async def _get_user(db: AsyncSession, clerk_user_id: str) -> User:
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def log_cardio(
    req: CardioLogRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_user(db, current_user.sub)

    log = CardioLog(
        id=uuid.uuid4(),
        user_id=user.id,
        session_id=uuid.UUID(req.session_id) if req.session_id else None,
        log_date=req.log_date or today_in_timezone(),
        cardio_type=req.cardio_type,
        performed=req.performed,
        duration_minutes=req.duration_minutes,
        calories_burned=req.calories_burned,
        distance_km=Decimal(str(req.distance_km)) if req.distance_km is not None else None,
        avg_heart_rate=req.avg_heart_rate,
        intensity=req.intensity,
        notes=req.notes,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    logger.info("Cardio logged", user_id=str(user.id), cardio_type=req.cardio_type)
    return _to_dict(log)


@router.get("/today")
async def get_today_cardio(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_user(db, current_user.sub)
    today = today_in_timezone()
    result = await db.execute(
        select(CardioLog)
        .where(CardioLog.user_id == user.id, CardioLog.log_date == today)
        .order_by(desc(CardioLog.created_at))
    )
    logs = result.scalars().all()
    return {"logs": [_to_dict(l) for l in logs], "date": today.isoformat()}


@router.get("")
async def list_cardio(
    days: int = 30,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from datetime import timedelta
    user = await _get_user(db, current_user.sub)
    since = today_in_timezone() - timedelta(days=days)
    result = await db.execute(
        select(CardioLog)
        .where(CardioLog.user_id == user.id, CardioLog.log_date >= since)
        .order_by(desc(CardioLog.log_date), desc(CardioLog.created_at))
    )
    logs = result.scalars().all()
    return {"logs": [_to_dict(l) for l in logs]}


@router.get("/session/{session_id}")
async def get_cardio_for_session(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_user(db, current_user.sub)
    result = await db.execute(
        select(CardioLog)
        .where(
            CardioLog.user_id == user.id,
            CardioLog.session_id == uuid.UUID(session_id),
        )
        .order_by(desc(CardioLog.created_at))
    )
    logs = result.scalars().all()
    return {"logs": [_to_dict(l) for l in logs]}


@router.patch("/{log_id}")
async def update_cardio(
    log_id: str,
    req: CardioLogRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_user(db, current_user.sub)
    result = await db.execute(
        select(CardioLog).where(
            CardioLog.id == uuid.UUID(log_id),
            CardioLog.user_id == user.id,
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cardio log not found")

    if req.log_date is not None:
        log.log_date = req.log_date
    log.cardio_type = req.cardio_type
    log.performed = req.performed
    log.duration_minutes = req.duration_minutes
    log.calories_burned = req.calories_burned
    log.distance_km = Decimal(str(req.distance_km)) if req.distance_km is not None else None
    log.avg_heart_rate = req.avg_heart_rate
    log.intensity = req.intensity
    log.notes = req.notes

    await db.commit()
    await db.refresh(log)
    return _to_dict(log)


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cardio(
    log_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    user = await _get_user(db, current_user.sub)
    result = await db.execute(
        delete(CardioLog).where(
            CardioLog.id == uuid.UUID(log_id),
            CardioLog.user_id == user.id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cardio log not found")
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
