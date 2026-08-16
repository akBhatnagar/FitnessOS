"""Notifications API — personalized daily tips + deterministic notifications."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import today_in_timezone
from app.core.logging import get_logger
from app.core.security import TokenPayload, get_current_user
from app.db.models.nutrition import Meal, MealItem
from app.db.models.user import User, UserPreferences
from app.db.models.workout import WorkoutSession
from app.db.session import get_db
from app.services.llm.provider import get_llm

logger = get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

# In-memory cache for daily tips — keyed by (user_id, date_str)
_daily_tip_cache: dict[str, dict] = {}


def _cache_key(user_id: str, date_str: str) -> str:
    return f"{user_id}:{date_str}"


def _cleanup_old_cache():
    """Remove cache entries older than 2 days."""
    cutoff = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    keys_to_remove = [k for k in _daily_tip_cache if k.split(":")[1] < cutoff]
    for k in keys_to_remove:
        del _daily_tip_cache[k]


async def _get_user(clerk_id: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
    user = result.scalar_one_or_none()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def _gather_user_stats(user: User, db: AsyncSession, today: date) -> dict:
    """Gather concise user stats for AI tip generation — minimal data, no raw dumps."""
    stats: dict = {}

    # Preferences
    prefs_result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    prefs = prefs_result.scalar_one_or_none()
    if prefs:
        stats["current_weight"] = float(prefs.current_weight_kg) if prefs.current_weight_kg else None
        stats["target_weight"] = float(prefs.target_weight_kg) if prefs.target_weight_kg else None
        stats["height_cm"] = float(prefs.height_cm) if prefs.height_cm else None

    # Recent workouts (last 7 days)
    week_ago = today - timedelta(days=7)
    workout_result = await db.execute(
        select(func.count(WorkoutSession.id)).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.session_date >= week_ago,
            WorkoutSession.status == "completed",
        )
    )
    stats["workouts_this_week"] = workout_result.scalar() or 0

    # Last 30 days workout count
    month_ago = today - timedelta(days=30)
    monthly_result = await db.execute(
        select(func.count(WorkoutSession.id)).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.session_date >= month_ago,
            WorkoutSession.status == "completed",
        )
    )
    stats["workouts_last_30_days"] = monthly_result.scalar() or 0

    # Today's nutrition so far
    meals_result = await db.execute(
        select(
            func.coalesce(func.sum(Meal.total_protein_g), 0).label("protein"),
            func.coalesce(func.sum(Meal.total_calories), 0).label("calories"),
        ).where(Meal.user_id == user.id, Meal.meal_date == today)
    )
    row = meals_result.one()
    stats["today_protein_g"] = float(row.protein)
    stats["today_calories"] = float(row.calories)

    # Yesterday's protein
    yesterday = today - timedelta(days=1)
    yesterday_result = await db.execute(
        select(
            func.coalesce(func.sum(Meal.total_protein_g), 0).label("protein"),
        ).where(Meal.user_id == user.id, Meal.meal_date == yesterday)
    )
    stats["yesterday_protein_g"] = float(yesterday_result.scalar() or 0)

    # Protein target
    if prefs and prefs.current_weight_kg:
        stats["protein_target_g"] = round(float(prefs.current_weight_kg) * 1.6)
    else:
        stats["protein_target_g"] = 160

    # Weight trend (compare current vs what we know)
    if stats.get("current_weight") and stats.get("target_weight"):
        diff = stats["current_weight"] - stats["target_weight"]
        stats["weight_to_lose_kg"] = round(diff, 1) if diff > 0 else 0

    # Rest days from preferences
    if prefs:
        stats["rest_days"] = prefs.rest_days or []

    return stats


async def _generate_daily_tip(user: User, db: AsyncSession, today: date) -> str:
    """Generate a personalized daily tip using AI with minimal context."""
    stats = await _gather_user_stats(user, db, today)

    # Build concise prompt
    context_lines = []
    if stats.get("current_weight"):
        context_lines.append(f"Current weight: {stats['current_weight']} kg")
    if stats.get("target_weight"):
        context_lines.append(f"Target weight: {stats['target_weight']} kg")
    if stats.get("weight_to_lose_kg"):
        context_lines.append(f"Weight to lose: {stats['weight_to_lose_kg']} kg")
    context_lines.append(f"Workouts this week: {stats.get('workouts_this_week', 0)}")
    context_lines.append(f"Workouts last 30 days: {stats.get('workouts_last_30_days', 0)}")
    context_lines.append(f"Today's protein so far: {stats.get('today_protein_g', 0)}g / {stats.get('protein_target_g', 160)}g target")
    context_lines.append(f"Yesterday's protein: {stats.get('yesterday_protein_g', 0)}g")
    context_lines.append(f"Today's calories so far: {stats.get('today_calories', 0)} kcal")
    context_lines.append(f"Day of week: {today.strftime('%A')}")

    context_str = "\n".join(context_lines)

    system_msg = (
        "You are a concise fitness coach. Generate ONE short personalized tip (1-2 sentences max) "
        "based on the user's current stats. Be specific and actionable. "
        "Do NOT use generic motivational fluff. Reference their actual numbers. "
        "Examples of good tips:\n"
        "- 'You've hit 4 workouts this week already. If you train today, focus on progressive overload rather than volume.'\n"
        "- 'Your protein was 40g short yesterday. Add a whey shake + paneer meal today to compensate.'\n"
        "- 'With 3.5 kg left to lose and consistent training, maintain your calorie target — no need to cut further.'\n"
        "Return ONLY the tip text, nothing else."
    )

    try:
        llm = get_llm(temperature=0.6, max_tokens=150)
        from langchain_core.messages import HumanMessage, SystemMessage
        response = await llm.ainvoke([
            SystemMessage(content=system_msg),
            HumanMessage(content=f"User stats for today ({today.isoformat()}):\n{context_str}"),
        ])
        tip = response.content.strip()
        if tip:
            return tip
    except Exception as e:
        logger.error("Failed to generate daily tip", error=str(e))

    # Fallback: deterministic tip based on stats
    if stats.get("workouts_this_week", 0) >= 5:
        return "You've trained hard this week. Consider an active recovery day — light stretching or a walk."
    if stats.get("yesterday_protein_g", 0) < stats.get("protein_target_g", 160) * 0.7:
        deficit = round(stats.get("protein_target_g", 160) - stats.get("yesterday_protein_g", 0))
        return f"Yesterday's protein was {deficit}g short of target. Prioritize protein-rich meals today."
    if stats.get("workouts_this_week", 0) == 0:
        return "No workouts logged this week yet. Even a 30-minute session will maintain your progress."
    return f"You've completed {stats.get('workouts_this_week', 0)} workouts this week. Stay consistent with your nutrition."


@router.get("/daily-tip")
async def get_daily_tip(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get today's personalized tip. Generated once per day and cached.
    """
    user = await _get_user(current_user.sub, db)
    today = today_in_timezone(user.timezone)
    date_str = today.isoformat()
    key = _cache_key(str(user.id), date_str)

    # Check cache
    if key in _daily_tip_cache:
        return _daily_tip_cache[key]

    # Cleanup old entries
    _cleanup_old_cache()

    # Generate new tip
    tip = await _generate_daily_tip(user, db, today)

    result = {
        "date": date_str,
        "tip": tip,
        "generated_at": datetime.now().isoformat(),
    }

    # Cache it
    _daily_tip_cache[key] = result

    return result
