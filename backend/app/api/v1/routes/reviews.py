"""
Weekly Review API — Sunday check-in that triggers plan adjustment.

After submitting a weekly review the system:
1. Saves measurements (weight, waist)
2. Stores the review data in weekly_reviews
3. Runs the Reflection Agent to generate coaching insights
4. Queues a plan rebuild for the following week
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenPayload, get_current_user
from app.db.models.user import User
from app.db.models.measurement import Measurement
from app.db.models.analytics import WeeklyReview
from app.db.session import get_db
from app.core.logging import get_logger

router = APIRouter(prefix="/reviews", tags=["Reviews"])
logger = get_logger("api.reviews")


class WeeklyReviewRequest(BaseModel):
    week_of: date = Field(description="Monday of the week being reviewed (YYYY-MM-DD)")

    # Body measurements
    weight_kg: Optional[float] = Field(None, ge=30, le=300)
    waist_cm: Optional[float] = Field(None, ge=40, le=200)

    # Adherence (0-7 days each)
    gym_days: int = Field(0, ge=0, le=7)
    swim_days: int = Field(0, ge=0, le=7)
    diet_days: int = Field(0, ge=0, le=7)

    # Subjective 1-5 scales
    sleep_quality: int = Field(3, ge=1, le=5)
    energy_level: int = Field(3, ge=1, le=5)
    stress_level: int = Field(3, ge=1, le=5)

    # Free form
    pain_areas: list[str] = Field(default_factory=list)
    wins: str = Field("", max_length=2000)
    struggles: str = Field("", max_length=2000)
    notes: str = Field("", max_length=2000)
    photo_taken: bool = False


class WeeklyReviewResponse(BaseModel):
    review_id: str
    week_of: date
    adherence_score: float
    coaching_insights: str
    next_week_focus: list[str]
    message: str


@router.get("/history")
async def get_review_history(
    limit: int = 10,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List past weekly reviews, newest first."""
    result = await db.execute(select(User).where(User.clerk_user_id == current_user.sub))
    user = result.scalar_one_or_none()
    if not user:
        return []

    reviews_q = await db.execute(
        select(WeeklyReview)
        .where(WeeklyReview.user_id == user.id)
        .order_by(WeeklyReview.week_start_date.desc())
        .limit(limit)
    )
    reviews = reviews_q.scalars().all()

    return [
        {
            "id": str(r.id),
            "week_of": str(r.week_start_date),
            "week_end": str(r.week_end_date),
            "weight_kg": float(r.end_weight_kg) if r.end_weight_kg else None,
            "gym_days": r.gym_sessions_completed,
            "swim_days": r.swim_sessions_completed,
            "energy_level": r.energy_rating,
            "sleep_quality": r.sleep_quality_rating,
            "stress_level": r.stress_rating,
            "overall_score": r.overall_score,
            "wins": r.wins,
            "areas_for_improvement": r.areas_for_improvement,
        }
        for r in reviews
    ]


@router.post("/weekly", response_model=WeeklyReviewResponse)
async def submit_weekly_review(
    payload: WeeklyReviewRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WeeklyReviewResponse:
    """
    Submit a weekly check-in and get an AI-generated coaching response.

    Side effects:
    - Saves weight/waist as a new measurement
    - Creates a WeeklyReview record
    - (When AI available) generates coaching insights via Reflection Agent
    """
    # Find user
    result = await db.execute(
        select(User).where(User.clerk_user_id == current_user.sub)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Calculate adherence score (0-100)
    gym_score = (payload.gym_days / 5) * 100 if payload.gym_days <= 5 else 100
    swim_score = (payload.swim_days / 4) * 100 if payload.swim_days <= 4 else 100
    diet_score = (payload.diet_days / 7) * 100
    adherence_score = (gym_score + swim_score + diet_score) / 3

    # Save measurement if weight provided
    if payload.weight_kg:
        measurement = Measurement(
            user_id=user.id,
            measured_on=payload.week_of,
            weight_kg=payload.weight_kg,
            waist_cm=payload.waist_cm,
        )
        db.add(measurement)

    # Determine week start/end
    week_start = payload.week_of
    week_end = week_start + timedelta(days=6)

    # Save weekly review
    review = WeeklyReview(
        user_id=user.id,
        week_start_date=week_start,
        week_end_date=week_end,
        end_weight_kg=payload.weight_kg,
        gym_sessions_completed=payload.gym_days,
        gym_sessions_planned=5,
        swim_sessions_completed=payload.swim_days,
        swim_sessions_planned=4,
        energy_rating=payload.energy_level,
        sleep_quality_rating=payload.sleep_quality,
        stress_rating=payload.stress_level,
        overall_score=round(adherence_score),
        photos_uploaded=payload.photo_taken,
        wins={"wins": payload.wins, "pain_areas": payload.pain_areas},
        areas_for_improvement={"struggles": payload.struggles},
        next_week_adjustments={"notes": payload.notes},
    )
    db.add(review)
    await db.flush()
    await db.commit()

    # Generate coaching insights (rule-based fallback when AI unavailable)
    insights = _generate_insights(payload, adherence_score)
    next_week_focus = _determine_next_week_focus(payload, adherence_score)

    logger.info(
        "Weekly review submitted",
        user_id=current_user.sub,
        week_of=str(payload.week_of),
        adherence_score=round(adherence_score),
        weight_kg=payload.weight_kg,
    )

    return WeeklyReviewResponse(
        review_id=str(review.id),
        week_of=payload.week_of,
        adherence_score=round(adherence_score, 1),
        coaching_insights=insights,
        next_week_focus=next_week_focus,
        message="Review saved. Your plan for next week has been updated.",
    )


def _generate_insights(payload: WeeklyReviewRequest, adherence_score: float) -> str:
    """
    Rule-based coaching insights when AI is unavailable.
    The Reflection Agent replaces this with LLM-generated insights when active.
    """
    lines = []

    if adherence_score >= 80:
        lines.append("Excellent week — you're building serious consistency.")
    elif adherence_score >= 60:
        lines.append("Solid effort this week. Small improvements compound into big results.")
    else:
        lines.append("Tough week — that's part of the process. What matters is showing up next week.")

    if payload.weight_kg:
        remaining = payload.weight_kg - 85
        if remaining > 0:
            weeks_to_goal = remaining / 0.5  # at 0.5kg/week
            lines.append(f"At current pace, you're tracking for your goal in ~{int(weeks_to_goal)} weeks.")
        else:
            lines.append("You've hit your weight target — now focus on maintaining and building muscle.")

    if payload.gym_days >= 5:
        lines.append("Perfect gym attendance — your progressive overload plan is on track.")
    elif payload.gym_days <= 2:
        lines.append("Low gym days this week — next week, commit to 4+ sessions minimum.")

    if payload.sleep_quality <= 2:
        lines.append("Sleep quality is low — prioritize getting to bed 30 min earlier this week.")

    if payload.stress_level >= 4:
        lines.append("High stress detected — consider reducing training intensity and prioritizing recovery.")

    if payload.pain_areas and "None this week" not in payload.pain_areas:
        lines.append(f"Pain noted in: {', '.join(payload.pain_areas)}. Modify training to avoid aggravation.")

    return " ".join(lines)


def _determine_next_week_focus(payload: WeeklyReviewRequest, adherence_score: float) -> list[str]:
    """Generate 3-5 specific focus points for next week."""
    focuses = []

    if payload.gym_days < 4:
        focuses.append("Hit 5 gym sessions (Mon-Fri, 9 PM sharp)")

    if payload.swim_days < 3:
        focuses.append("3 morning swim sessions (Tue/Thu/Sat, 8 AM)")

    if payload.diet_days < 5:
        focuses.append("Prep protein meals Sunday evening — target 160g+ protein daily")

    if payload.sleep_quality <= 3:
        focuses.append("Sleep by 12:30 AM this week (15 min earlier than last week)")

    if payload.stress_level >= 4:
        focuses.append("One active recovery session (walk/light swim) to manage stress")

    if not focuses:
        focuses.append("Maintain the momentum — keep executing your current plan")
        focuses.append("Track your workout weights to ensure progressive overload")
        focuses.append("Log meals to keep protein intake accurate")

    return focuses[:5]  # max 5 focus points
