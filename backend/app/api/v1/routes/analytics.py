"""
Analytics API — weight trends, adherence, predictions, and AI insights.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenPayload, get_current_user
from app.db.models.user import User, UserPreferences
from app.db.models.measurement import Measurement
from app.db.models.workout import WorkoutSession, SessionStatus
from app.db.models.nutrition import Meal
from app.db.models.analytics import WeeklyReview
from app.db.models.event import Event
from app.db.session import get_db

router = APIRouter(prefix="/analytics", tags=["Analytics"])


async def _get_user(clerk_id: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
    return result.scalar_one_or_none()


@router.get("/overview")
async def get_analytics_overview(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Full analytics overview for the analytics dashboard.
    Includes: weight history, gym adherence, macro trends, event countdowns, predictions.
    """
    user = await _get_user(current_user.sub, db)
    if not user:
        return {}

    today = date.today()
    twelve_weeks_ago = today - timedelta(weeks=12)
    four_weeks_ago = today - timedelta(weeks=4)

    # ─── Weight History (12 weeks) ────────────────────────────────────────
    weight_result = await db.execute(
        select(Measurement.measured_on, Measurement.weight_kg)
        .where(
            Measurement.user_id == user.id,
            Measurement.weight_kg.isnot(None),
            Measurement.measured_on >= twelve_weeks_ago,
        )
        .order_by(Measurement.measured_on)
    )
    weight_rows = weight_result.fetchall()
    weight_history = [
        {"date": row.measured_on.isoformat(), "weight_kg": float(row.weight_kg)}
        for row in weight_rows
    ]

    # Get current and starting weight
    current_weight = float(weight_rows[-1].weight_kg) if weight_rows else 100.0
    start_weight = float(weight_rows[0].weight_kg) if weight_rows else 100.0
    total_lost = round(start_weight - current_weight, 1)

    # ─── Gym Adherence (last 4 weeks, simple query) ──────────────────────
    gym_result = await db.execute(
        select(
            WorkoutSession.scheduled_date,
            WorkoutSession.status,
        )
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.scheduled_date >= four_weeks_ago,
        )
        .order_by(WorkoutSession.scheduled_date)
    )
    gym_rows = gym_result.fetchall()

    # Group by week manually
    from collections import defaultdict
    week_map: dict = defaultdict(lambda: {"completed": 0, "total": 0})
    for row in gym_rows:
        # Monday of the week
        monday = row.scheduled_date - timedelta(days=row.scheduled_date.weekday())
        key = monday.strftime("%b %d")
        week_map[key]["total"] += 1
        if str(row.status) in ("completed", "SessionStatus.COMPLETED"):
            week_map[key]["completed"] += 1

    gym_adherence = [
        {
            "week": week,
            "completed": data["completed"],
            "total": data["total"],
            "pct": round(data["completed"] / data["total"] * 100) if data["total"] > 0 else 0,
        }
        for week, data in sorted(week_map.items())
    ]

    # ─── Macro Trends (last 2 weeks) ──────────────────────────────────────
    two_weeks_ago = today - timedelta(weeks=2)
    macro_result = await db.execute(
        select(
            Meal.meal_date,
            func.coalesce(func.sum(Meal.total_calories), 0).label("calories"),
            func.coalesce(func.sum(Meal.total_protein_g), 0).label("protein_g"),
        )
        .where(Meal.user_id == user.id, Meal.meal_date >= two_weeks_ago)
        .group_by(Meal.meal_date)
        .order_by(Meal.meal_date)
    )
    macro_rows = macro_result.fetchall()
    macro_trend = [
        {
            "date": row.meal_date.isoformat(),
            "calories": round(float(row.calories)),
            "protein_g": round(float(row.protein_g), 1),
        }
        for row in macro_rows
    ]

    # ─── Event Countdowns ─────────────────────────────────────────────────
    event_result = await db.execute(
        select(Event)
        .where(
            Event.user_id == user.id,
            Event.is_active.is_(True),
            Event.event_date >= today,
        )
        .order_by(Event.event_date)
    )
    events = event_result.scalars().all()
    event_countdowns = [
        {
            "title": e.title,
            "event_type": e.event_type,
            "date": e.event_date.isoformat(),
            "days_remaining": e.days_remaining,
            "peak_priority": e.peak_priority,
            "is_critical": e.is_critical,
        }
        for e in events
    ]

    # ─── Wedding Weight Prediction ────────────────────────────────────────
    wedding = next((e for e in events if "wedding" in str(e.event_type).lower()), None)
    prediction = None
    if wedding:
        days_to_wedding = wedding.days_remaining
        weeks_to_wedding = days_to_wedding / 7

        # Rate of loss: average from last 4 weeks
        if len(weight_rows) >= 2:
            recent_loss = float(weight_rows[0].weight_kg) - float(weight_rows[-1].weight_kg)
            weeks_elapsed = (weight_rows[-1].measured_on - weight_rows[0].measured_on).days / 7
            weekly_rate = recent_loss / max(weeks_elapsed, 1) if weeks_elapsed > 0 else 0.3
        else:
            weekly_rate = 0.3  # conservative estimate

        predicted_wedding_weight = max(78.0, round(current_weight - (weekly_rate * weeks_to_wedding), 1))
        kg_to_lose = round(current_weight - 85.0, 1)

        prediction = {
            "event": wedding.title,
            "event_date": wedding.event_date.isoformat(),
            "days_remaining": days_to_wedding,
            "current_weight": current_weight,
            "target_weight": 85.0,
            "predicted_weight": predicted_wedding_weight,
            "weekly_loss_rate": round(weekly_rate, 2),
            "on_track": predicted_wedding_weight <= 85.5,
            "kg_to_lose": kg_to_lose,
            "confidence": "high" if len(weight_rows) >= 4 else "low",
        }

    # ─── Weekly Reviews (last 4) ──────────────────────────────────────────
    review_result = await db.execute(
        select(WeeklyReview)
        .where(WeeklyReview.user_id == user.id)
        .order_by(desc(WeeklyReview.week_start_date))
        .limit(4)
    )
    reviews = review_result.scalars().all()
    review_scores = [
        {
            "week": r.week_start_date.strftime("Week of %b %d"),
            "score": r.overall_score,
            "gym": r.gym_sessions_completed,
            "swim": r.swim_sessions_completed,
        }
        for r in reviews
    ]

    # ─── Summary Stats ────────────────────────────────────────────────────
    total_workouts = await db.execute(
        select(func.count()).select_from(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == SessionStatus.COMPLETED,
        )
    )
    total_gym = total_workouts.scalar_one() or 0

    return {
        "weight_history": weight_history,
        "weight_summary": {
            "current_kg": current_weight,
            "target_kg": 85.0,
            "total_lost_kg": total_lost,
            "to_go_kg": max(0, round(current_weight - 85.0, 1)),
            "weeks_of_data": len(weight_rows),
        },
        "gym_adherence": gym_adherence,
        "macro_trend": macro_trend,
        "event_countdowns": event_countdowns,
        "wedding_prediction": prediction,
        "weekly_review_scores": list(reversed(review_scores)),
        "lifetime_stats": {
            "total_gym_sessions": total_gym,
        },
    }
