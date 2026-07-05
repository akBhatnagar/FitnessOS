"""
Dashboard API — aggregated data for the main dashboard view.

Returns all data needed to render the dashboard in a single request.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenPayload, get_current_user
from app.db.models.measurement import Measurement
from app.db.models.user import User, UserPreferences
from app.db.models.workout import WorkoutSession, SessionStatus
from app.db.models.swimming import SwimmingSession
from app.db.models.analytics import Achievement, Prediction
from app.db.models.event import Event
from app.db.session import get_db

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Event dates are always calculated dynamically
PRE_WEDDING_DATE = date(2026, 10, 20)
WEDDING_DATE = date(2027, 1, 30)


@router.get("/summary")
async def get_dashboard_summary(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return all data needed to render the main dashboard.

    This endpoint is optimized for the dashboard load — it aggregates data
    from multiple tables in a single call to minimize round trips.
    """
    today = date.today()

    result = await db.execute(
        select(User, UserPreferences)
        .outerjoin(UserPreferences, User.id == UserPreferences.user_id)
        .where(User.clerk_user_id == current_user.sub)
    )
    row = result.first()
    if not row:
        return {}

    user, prefs = row

    # Recent measurements
    m_result = await db.execute(
        select(Measurement)
        .where(Measurement.user_id == user.id)
        .order_by(Measurement.measured_on.desc())
        .limit(7)
    )
    measurements = m_result.scalars().all()
    latest = measurements[0] if measurements else None

    # This week's sessions
    week_start = today - timedelta(days=today.weekday())
    week_sessions_result = await db.execute(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.scheduled_date >= week_start,
            WorkoutSession.scheduled_date <= today,
        )
    )
    week_sessions = week_sessions_result.scalars().all()
    completed_sessions = sum(1 for s in week_sessions if s.status == SessionStatus.COMPLETED)

    # Upcoming events
    events_result = await db.execute(
        select(Event)
        .where(
            Event.user_id == user.id,
            Event.is_active == True,  # noqa: E712
            Event.event_date >= today,
        )
        .order_by(Event.event_date)
        .limit(5)
    )
    events = events_result.scalars().all()

    # Recent achievements
    achievements_result = await db.execute(
        select(Achievement)
        .where(Achievement.user_id == user.id)
        .order_by(Achievement.achieved_on.desc())
        .limit(3)
    )
    achievements = achievements_result.scalars().all()

    # Latest prediction
    pred_result = await db.execute(
        select(Prediction)
        .where(
            Prediction.user_id == user.id,
            Prediction.prediction_type == "weight_on_wedding_day",
        )
        .order_by(Prediction.created_at.desc())
        .limit(1)
    )
    prediction = pred_result.scalar_one_or_none()

    return {
        "user": {
            "name": user.full_name,
            "is_onboarded": user.is_onboarded,
        },
        "metrics": {
            "current_weight_kg": float(latest.weight_kg) if latest and latest.weight_kg else None,
            "target_weight_kg": float(prefs.target_weight_kg) if prefs and prefs.target_weight_kg else 85,
            "weight_to_lose_kg": (
                float(latest.weight_kg) - float(prefs.target_weight_kg)
                if latest and latest.weight_kg and prefs and prefs.target_weight_kg
                else None
            ),
            "body_fat_pct": float(latest.body_fat_pct) if latest and latest.body_fat_pct else None,
            "waist_cm": float(latest.waist_cm) if latest and latest.waist_cm else None,
        },
        "weekly_progress": {
            "gym_sessions_completed": completed_sessions,
            "gym_sessions_scheduled": len(week_sessions),
            "adherence_pct": round(completed_sessions / max(len(week_sessions), 1) * 100),
        },
        "weight_history": [
            {
                "date": m.measured_on.isoformat(),
                "weight_kg": float(m.weight_kg) if m.weight_kg else None,
            }
            for m in reversed(measurements)
        ],
        "countdowns": {
            "pre_wedding": {
                "title": "Pre-Wedding Shoot",
                "date": PRE_WEDDING_DATE.isoformat(),
                "days_remaining": (PRE_WEDDING_DATE - today).days,
            },
            "wedding": {
                "title": "Wedding",
                "date": WEDDING_DATE.isoformat(),
                "days_remaining": (WEDDING_DATE - today).days,
            },
        },
        "upcoming_events": [
            {
                "id": str(e.id),
                "title": e.title,
                "type": e.event_type,
                "date": e.event_date.isoformat(),
                "days_remaining": (e.event_date - today).days,
                "is_critical": e.peak_priority in ("critical", "high"),
            }
            for e in events
        ],
        "recent_achievements": [
            {
                "title": a.title,
                "type": a.achievement_type,
                "achieved_on": a.achieved_on.isoformat(),
                "icon": a.icon,
            }
            for a in achievements
        ],
        "prediction": {
            "predicted_wedding_weight_kg": float(prediction.predicted_value) if prediction else None,
            "confidence_pct": float(prediction.confidence_pct) if prediction else None,
        } if prediction else None,
        "today": today.isoformat(),
    }
