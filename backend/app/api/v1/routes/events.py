"""Events API — list and update milestone events (wedding, trips, etc.)."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import today_in_timezone
from app.core.security import TokenPayload, get_current_user
from app.db.models.event import Event
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(prefix="/events", tags=["Events"])


class EventUpdateRequest(BaseModel):
    event_date: date | None = None
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    location: str | None = Field(None, max_length=255)
    is_active: bool | None = None


def _event_payload(event: Event, today: date) -> dict:
    days = (event.event_date - today).days
    return {
        "id": str(event.id),
        "title": event.title,
        "description": event.description,
        "event_type": str(event.event_type),
        "event_date": event.event_date.isoformat(),
        "location": event.location,
        "is_active": event.is_active,
        "peak_priority": str(event.peak_priority),
        "days_remaining": days,
        "is_critical": 0 < days <= 30,
        "is_upcoming": days >= 0,
    }


async def _get_user(clerk_id: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/")
async def list_events(
    include_past: bool = False,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List the user's active events, soonest first."""
    user = await _get_user(current_user.sub, db)
    today = today_in_timezone(user.timezone)

    query = select(Event).where(
        Event.user_id == user.id,
        Event.is_active.is_(True),
    )
    if not include_past:
        query = query.where(Event.event_date >= today)
    query = query.order_by(Event.event_date)

    result = await db.execute(query)
    events = result.scalars().all()
    return [_event_payload(e, today) for e in events]


@router.patch("/{event_id}")
async def update_event(
    event_id: str,
    request: EventUpdateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update an event — primarily used to change the event date."""
    user = await _get_user(current_user.sub, db)
    today = today_in_timezone(user.timezone)

    try:
        eid = uuid.UUID(event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid event id") from exc

    result = await db.execute(
        select(Event).where(Event.id == eid, Event.user_id == user.id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    updates = request.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "event_date" in updates and updates["event_date"] is not None:
        if updates["event_date"] < today:
            raise HTTPException(
                status_code=400,
                detail="Event date cannot be in the past",
            )

    for field, value in updates.items():
        setattr(event, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(event)

    return _event_payload(event, today)
