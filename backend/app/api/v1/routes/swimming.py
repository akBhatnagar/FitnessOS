"""
Swimming Tracker API — session logging and progress tracking.

Endpoints:
- GET  /swimming/sessions        — list recent sessions
- POST /swimming/sessions        — log a new session
- GET  /swimming/sessions/:id    — session detail
- GET  /swimming/stats           — aggregate stats and skill level
- GET  /swimming/milestones      — progression milestones
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenPayload, get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.core.logging import get_logger

router = APIRouter(prefix="/swimming", tags=["Swimming"])
logger = get_logger("api.swimming")


# ─── Request / Response Models ────────────────────────────────────────────────

class LogSwimmingSessionRequest(BaseModel):
    session_date: date = Field(default_factory=date.today)
    duration_minutes: int = Field(ge=5, le=240)
    laps_completed: Optional[int] = Field(None, ge=0, description="Number of laps (25m pool default)")
    distance_meters: Optional[int] = Field(None, ge=0)
    pool_length_m: int = Field(25, description="Pool length in metres")
    stroke_type: str = Field("freestyle", description="freestyle, breaststroke, backstroke, butterfly, mixed")
    drill_focus: Optional[str] = Field(None, description="e.g., breathing, flip turns, kick")
    perceived_effort: Optional[int] = Field(None, ge=1, le=10)
    heart_rate_avg: Optional[int] = Field(None, ge=40, le=220)
    notes: Optional[str] = Field(None, max_length=1000)


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_user(clerk_id: str, db: AsyncSession) -> User:
    from fastapi import HTTPException
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _assess_skill_level(total_sessions: int, best_distance_m: int) -> dict:
    """Determine skill level from session count and distance covered."""
    if total_sessions == 0:
        return {"level": "beginner", "label": "Beginner", "emoji": "🌊"}
    if best_distance_m < 200 or total_sessions < 5:
        return {"level": "beginner", "label": "Beginner", "emoji": "🌊"}
    if best_distance_m < 500 or total_sessions < 15:
        return {"level": "developing", "label": "Developing", "emoji": "🏊"}
    if best_distance_m < 1000 or total_sessions < 30:
        return {"level": "intermediate", "label": "Intermediate", "emoji": "🏊‍♂️"}
    return {"level": "advanced", "label": "Advanced", "emoji": "🥇"}


MILESTONES = [
    {"id": 1, "title": "First Lap",       "description": "Complete your first 25m lap without stopping",  "target_m": 25,   "target_sessions": 1},
    {"id": 2, "title": "Pool Length x4",  "description": "Swim 100m continuously",                        "target_m": 100,  "target_sessions": 3},
    {"id": 3, "title": "Quarter K",       "description": "Reach 250m in a single session",                "target_m": 250,  "target_sessions": 8},
    {"id": 4, "title": "Half Kilometre",  "description": "Complete 500m without a break",                  "target_m": 500,  "target_sessions": 15},
    {"id": 5, "title": "1K Club",         "description": "Hit the 1,000m milestone",                       "target_m": 1000, "target_sessions": 30},
    {"id": 6, "title": "Open Water Ready","description": "Sustain 1,500m at a steady pace",                "target_m": 1500, "target_sessions": 50},
]


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    limit: int = Query(20, le=50),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List recent swimming sessions, newest first."""
    user = await _get_user(current_user.sub, db)

    rows = await db.execute(
        text("""
            SELECT id, session_date, duration_minutes, total_laps, total_meters,
                   pool_length_m, strokes_practiced, notes, created_at
            FROM swimming_sessions
            WHERE user_id = :uid
            ORDER BY session_date DESC, created_at DESC
            LIMIT :lim
        """),
        {"uid": str(user.id), "lim": limit},
    )
    sessions = rows.mappings().all()

    return [
        {
            "id": str(s["id"]),
            "session_date": str(s["session_date"]),
            "duration_minutes": s["duration_minutes"],
            "laps_completed": s["total_laps"],
            "distance_meters": s["total_meters"],
            "pool_length_m": s["pool_length_m"],
            "stroke_type": s["strokes_practiced"][0] if s["strokes_practiced"] else "freestyle",
            "notes": s["notes"],
        }
        for s in sessions
    ]


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def log_session(
    request: LogSwimmingSessionRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Log a swimming session."""
    user = await _get_user(current_user.sub, db)

    distance = request.distance_meters
    if distance is None and request.laps_completed is not None:
        distance = request.laps_completed * request.pool_length_m

    # Map friendly field names → actual DB column names
    session_id = str(uuid4())
    await db.execute(
        text("""
            INSERT INTO swimming_sessions
                (id, user_id, session_date, completed, duration_minutes,
                 total_laps, total_meters, pool_length_m,
                 strokes_practiced, milestones_achieved, notes)
            VALUES
                (:id, :uid, :date, true, :dur,
                 :laps, :dist, :pool,
                 ARRAY[:stroke]::varchar[], ARRAY[]::varchar[], :notes)
        """),
        {
            "id": session_id,
            "uid": str(user.id),
            "date": request.session_date,
            "dur": request.duration_minutes,
            "laps": request.laps_completed,
            "dist": distance,
            "pool": request.pool_length_m,
            "stroke": request.stroke_type,
            "notes": request.notes or "",
        },
    )
    await db.commit()

    logger.info("Swimming session logged", user=current_user.sub, distance_m=distance)
    return {
        "id": session_id,
        "session_date": str(request.session_date),
        "distance_meters": distance,
        "duration_minutes": request.duration_minutes,
        "message": "Session logged successfully",
    }


@router.get("/stats")
async def get_stats(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aggregate swimming stats: totals, averages, skill level, and streak."""
    user = await _get_user(current_user.sub, db)

    agg = await db.execute(
        text("""
            SELECT
                COUNT(*)                          AS total_sessions,
                COALESCE(SUM(total_meters),0)     AS total_distance_m,
                COALESCE(SUM(duration_minutes),0) AS total_duration_min,
                COALESCE(MAX(total_meters),0)     AS best_distance_m,
                0                                 AS avg_effort
            FROM swimming_sessions
            WHERE user_id = :uid
        """),
        {"uid": str(user.id)},
    )
    row = agg.mappings().one()

    # Last 7-day sessions for streak
    recent = await db.execute(
        text("""
            SELECT DISTINCT session_date FROM swimming_sessions
            WHERE user_id = :uid AND session_date >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY session_date DESC
        """),
        {"uid": str(user.id)},
    )
    recent_dates = [r["session_date"] for r in recent.mappings().all()]

    # Weekly session count (this week Mon-Sun)
    week_count_q = await db.execute(
        text("""
            SELECT COUNT(*) AS cnt FROM swimming_sessions
            WHERE user_id = :uid
              AND session_date >= DATE_TRUNC('week', CURRENT_DATE)
              AND session_date < DATE_TRUNC('week', CURRENT_DATE) + INTERVAL '7 days'
        """),
        {"uid": str(user.id)},
    )
    week_count = week_count_q.mappings().one()["cnt"]

    skill = _assess_skill_level(int(row["total_sessions"]), int(row["best_distance_m"]))

    # Next milestone
    next_milestone = None
    for m in MILESTONES:
        if int(row["best_distance_m"]) < m["target_m"]:
            gap = m["target_m"] - int(row["best_distance_m"])
            next_milestone = {**m, "gap_meters": gap}
            break

    return {
        "total_sessions": int(row["total_sessions"]),
        "total_distance_km": round(int(row["total_distance_m"]) / 1000, 2),
        "total_duration_hours": round(int(row["total_duration_min"]) / 60, 1),
        "best_session_m": int(row["best_distance_m"]),
        "avg_effort": round(float(row["avg_effort"]), 1),
        "sessions_this_week": int(week_count),
        "skill_level": skill,
        "next_milestone": next_milestone,
        "recent_dates": [str(d) for d in recent_dates[:10]],
    }


@router.get("/milestones")
async def get_milestones(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """All milestones with completion status."""
    user = await _get_user(current_user.sub, db)

    agg = await db.execute(
        text("SELECT COALESCE(MAX(total_meters),0) AS best, COUNT(*) AS cnt FROM swimming_sessions WHERE user_id = :uid"),
        {"uid": str(user.id)},
    )
    row = agg.mappings().one()
    best_dist = int(row["best"])
    session_count = int(row["cnt"])

    return [
        {
            **m,
            "achieved": best_dist >= m["target_m"] and session_count >= m["target_sessions"],
        }
        for m in MILESTONES
    ]
