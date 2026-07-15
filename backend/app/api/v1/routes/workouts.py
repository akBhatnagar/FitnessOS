"""
Workout Tracker API — full CRUD for sessions, sets, and exercise library.

Endpoints:
- GET  /workouts/exercises         — search exercise library
- GET  /workouts/exercises/:id     — exercise detail + history + 1RM
- GET  /workouts/sessions/today    — today's sessions
- GET  /workouts/sessions/history  — recent session history
- POST /workouts/sessions          — create a new session
- POST /workouts/sessions/:id/start    — mark session started
- POST /workouts/sessions/:id/complete — complete session + log all sets
- POST /workouts/sessions/:id/sets     — add/update a set live
- GET  /workouts/sessions/:id/suggest  — progressive overload suggestion for this session
- GET  /workouts/plans/active          — active workout plan
- POST /workouts/plans/generate        — generate a new Push/Pull/Legs plan
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import TokenPayload, get_current_user
from app.db.models.user import User
from app.db.models.workout import Exercise, SessionStatus, WorkoutPlan, WorkoutSession, WorkoutSet
from app.db.session import get_db
from app.services.training.progressive_overload import (
    ExercisePerformance,
    ProgressionStrategy,
    SetRecord,
    calculate_progression,
    estimate_1rm,
    generate_legs_session,
    generate_pull_session,
    generate_push_session,
)

router = APIRouter(prefix="/workouts", tags=["Workouts"])
logger = get_logger("api.workouts")


# ─── Request / Response Models ───────────────────────────────────────────────

class SetLogRequest(BaseModel):
    exercise_id: str
    set_number: int = Field(ge=1, le=20)
    planned_reps: Optional[int] = None
    planned_weight_kg: Optional[float] = None
    actual_reps: Optional[int] = Field(None, ge=0, le=100)
    actual_weight_kg: Optional[float] = Field(None, ge=0, le=500)
    rpe: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None


class CompleteSessionRequest(BaseModel):
    effort_rating: Optional[int] = Field(None, ge=1, le=10)
    fatigue_rating: Optional[int] = Field(None, ge=1, le=10)
    mood_rating: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None


class CreateSessionRequest(BaseModel):
    session_name: str = Field(min_length=1, max_length=255)
    scheduled_date: date
    muscle_groups: list[str] = []
    planned_exercises: list[str] = []  # exercise IDs


class GeneratePlanRequest(BaseModel):
    plan_type: str = Field("ppl", description="ppl (Push/Pull/Legs), upper_lower, full_body")
    days_per_week: int = Field(5, ge=3, le=6)
    goal: str = Field("hypertrophy", description="hypertrophy, strength, fat_loss")


# ─── Helper — resolve user ────────────────────────────────────────────────────

async def _get_user(clerk_id: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ─── Exercise Library ────────────────────────────────────────────────────────

@router.get("/exercises")
async def search_exercises(
    query: str = "",
    muscle_group: str | None = None,
    tag: str | None = None,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Search the exercise library with optional filters."""
    stmt = select(Exercise)
    if query:
        stmt = stmt.where(Exercise.name.ilike(f"%{query}%"))
    if muscle_group:
        stmt = stmt.where(Exercise.primary_muscle == muscle_group)
    if tag:
        stmt = stmt.where(Exercise.tags.any(tag))
    stmt = stmt.order_by(Exercise.name).limit(60)

    result = await db.execute(stmt)
    exercises = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "name": e.name,
            "slug": e.slug,
            "type": e.exercise_type,
            "primary_muscle": e.primary_muscle,
            "secondary_muscles": e.secondary_muscles,
            "equipment": e.equipment_needed,
            "is_compound": e.is_compound,
            "tags": e.tags,
            "instructions": e.instructions,
            "tips": e.tips,
        }
        for e in exercises
    ]


@router.get("/exercises/{exercise_id}")
async def get_exercise_detail(
    exercise_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get exercise details including user's personal bests and history."""
    user = await _get_user(current_user.sub, db)

    result = await db.execute(
        select(Exercise).where(Exercise.id == uuid.UUID(exercise_id))
    )
    exercise = result.scalar_one_or_none()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    # Get best set (highest 1RM)
    best_result = await db.execute(
        select(
            WorkoutSet.actual_weight_kg,
            WorkoutSet.actual_reps,
            WorkoutSession.scheduled_date,
        )
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .where(
            WorkoutSet.exercise_id == exercise.id,
            WorkoutSession.user_id == user.id,
            WorkoutSet.actual_weight_kg.isnot(None),
            WorkoutSet.actual_reps.isnot(None),
        )
        .order_by(
            desc(WorkoutSet.actual_weight_kg * (1 + WorkoutSet.actual_reps / 30))
        )
        .limit(1)
    )
    best_row = best_result.first()

    # Get last 5 sessions this exercise was done
    history_result = await db.execute(
        select(
            WorkoutSet.actual_weight_kg,
            WorkoutSet.actual_reps,
            WorkoutSet.rpe,
            WorkoutSet.set_number,
            WorkoutSession.scheduled_date,
        )
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .where(
            WorkoutSet.exercise_id == exercise.id,
            WorkoutSession.user_id == user.id,
            WorkoutSet.actual_weight_kg.isnot(None),
        )
        .order_by(desc(WorkoutSession.scheduled_date), WorkoutSet.set_number)
        .limit(20)
    )
    history = history_result.fetchall()

    personal_best = None
    if best_row and best_row.actual_weight_kg and best_row.actual_reps:
        personal_best = {
            "weight_kg": float(best_row.actual_weight_kg),
            "reps": best_row.actual_reps,
            "estimated_1rm": round(estimate_1rm(float(best_row.actual_weight_kg), best_row.actual_reps), 1),
            "date": best_row.scheduled_date.isoformat(),
        }

    return {
        "id": str(exercise.id),
        "name": exercise.name,
        "slug": exercise.slug,
        "type": exercise.exercise_type,
        "primary_muscle": exercise.primary_muscle,
        "secondary_muscles": exercise.secondary_muscles,
        "equipment": exercise.equipment_needed,
        "is_compound": exercise.is_compound,
        "tags": exercise.tags,
        "instructions": exercise.instructions,
        "tips": exercise.tips,
        "personal_best": personal_best,
        "recent_history": [
            {
                "date": row.scheduled_date.isoformat(),
                "set": row.set_number,
                "weight_kg": float(row.actual_weight_kg),
                "reps": row.actual_reps,
                "rpe": row.rpe,
            }
            for row in history
        ],
    }


# ─── Sessions ─────────────────────────────────────────────────────────────────

@router.get("/sessions/today")
async def get_todays_sessions(
    date_param: Optional[date] = Query(None, alias="date", description="YYYY-MM-DD, defaults to today"),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Scheduled workout sessions for a given day (defaults to today)."""
    user = await _get_user(current_user.sub, db)
    target_date = date_param or date.today()
    if target_date > date.today():
        raise HTTPException(status_code=400, detail="Cannot view future dates")

    result = await db.execute(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.scheduled_date == target_date,
        )
        .order_by(WorkoutSession.created_at)
    )
    sessions = result.scalars().all()

    output = []
    for s in sessions:
        sets_count = await db.execute(
            select(func.count()).select_from(WorkoutSet).where(WorkoutSet.session_id == s.id)
        )
        output.append({
            "id": str(s.id),
            "session_name": s.session_name,
            "scheduled_date": s.scheduled_date.isoformat(),
            "status": s.status,
            "muscle_groups": s.muscle_groups_targeted,
            "duration_minutes": s.duration_minutes,
            "sets_logged": sets_count.scalar_one(),
            "effort_rating": s.effort_rating,
        })
    return output


@router.get("/sessions/history")
async def get_session_history(
    limit: int = 20,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Recent completed workout sessions."""
    user = await _get_user(current_user.sub, db)

    result = await db.execute(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == SessionStatus.COMPLETED,
        )
        .order_by(desc(WorkoutSession.scheduled_date))
        .limit(min(limit, 50))
    )
    sessions = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "session_name": s.session_name,
            "date": s.scheduled_date.isoformat(),
            "duration_minutes": s.duration_minutes,
            "muscle_groups": s.muscle_groups_targeted,
            "effort_rating": s.effort_rating,
            "fatigue_rating": s.fatigue_rating,
        }
        for s in sessions
    ]


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually create a workout session."""
    user = await _get_user(current_user.sub, db)

    if request.scheduled_date > date.today():
        raise HTTPException(status_code=400, detail="Cannot schedule workouts for future dates")

    session = WorkoutSession(
        user_id=user.id,
        session_name=request.session_name,
        scheduled_date=request.scheduled_date,
        muscle_groups_targeted=request.muscle_groups,
        status=SessionStatus.SCHEDULED,
    )
    db.add(session)
    await db.flush()
    await db.commit()

    return {"id": str(session.id), "session_name": session.session_name, "status": session.status}


@router.post("/sessions/{session_id}/start")
async def start_session(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark session as in-progress (started)."""
    user = await _get_user(current_user.sub, db)

    result = await db.execute(
        select(WorkoutSession).where(
            WorkoutSession.id == uuid.UUID(session_id),
            WorkoutSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.status = SessionStatus.IN_PROGRESS
    session.started_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "started", "started_at": session.started_at.isoformat()}


@router.post("/sessions/{session_id}/sets")
async def log_set(
    session_id: str,
    request: SetLogRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Log a single set during a live workout.

    Called after each set is completed. Supports real-time tracking.
    Returns the logged set + updated 1RM estimate.
    """
    user = await _get_user(current_user.sub, db)

    # Verify session belongs to user
    session_result = await db.execute(
        select(WorkoutSession).where(
            WorkoutSession.id == uuid.UUID(session_id),
            WorkoutSession.user_id == user.id,
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Upsert the set (same session + exercise + set_number)
    existing_result = await db.execute(
        select(WorkoutSet).where(
            WorkoutSet.session_id == session.id,
            WorkoutSet.exercise_id == uuid.UUID(request.exercise_id),
            WorkoutSet.set_number == request.set_number,
        )
    )
    workout_set = existing_result.scalar_one_or_none()

    if workout_set:
        workout_set.actual_weight_kg = request.actual_weight_kg
        workout_set.actual_reps = request.actual_reps
        workout_set.rpe = request.rpe
        workout_set.notes = request.notes
    else:
        workout_set = WorkoutSet(
            session_id=session.id,
            exercise_id=uuid.UUID(request.exercise_id),
            set_number=request.set_number,
            planned_reps=request.planned_reps,
            planned_weight_kg=request.planned_weight_kg,
            actual_reps=request.actual_reps,
            actual_weight_kg=request.actual_weight_kg,
            rpe=request.rpe,
            notes=request.notes,
        )
        db.add(workout_set)

    await db.flush()
    await db.commit()

    # Calculate 1RM if possible
    one_rm = None
    if request.actual_weight_kg and request.actual_reps:
        one_rm = round(estimate_1rm(request.actual_weight_kg, request.actual_reps), 1)

    return {
        "set_id": str(workout_set.id),
        "set_number": request.set_number,
        "weight_kg": request.actual_weight_kg,
        "reps": request.actual_reps,
        "rpe": request.rpe,
        "estimated_1rm": one_rm,
    }


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: str,
    request: CompleteSessionRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark session as completed and calculate duration."""
    user = await _get_user(current_user.sub, db)

    result = await db.execute(
        select(WorkoutSession).where(
            WorkoutSession.id == uuid.UUID(session_id),
            WorkoutSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    now = datetime.now(timezone.utc)
    session.status = SessionStatus.COMPLETED
    session.completed_at = now
    session.effort_rating = request.effort_rating
    session.fatigue_rating = request.fatigue_rating
    session.mood_rating = request.mood_rating
    session.notes = request.notes

    if session.started_at:
        duration = (now - session.started_at).seconds // 60
        session.duration_minutes = duration

    await db.commit()

    logger.info("Workout session completed", session_id=session_id, duration=session.duration_minutes)

    return {
        "status": "completed",
        "duration_minutes": session.duration_minutes,
        "session_id": session_id,
    }


@router.get("/sessions/{session_id}/sets")
async def get_session_sets(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get all sets logged for a session, grouped by exercise."""
    user = await _get_user(current_user.sub, db)

    result = await db.execute(
        select(WorkoutSet, Exercise.name, Exercise.primary_muscle)
        .join(Exercise, WorkoutSet.exercise_id == Exercise.id)
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .where(
            WorkoutSet.session_id == uuid.UUID(session_id),
            WorkoutSession.user_id == user.id,
        )
        .order_by(WorkoutSet.exercise_id, WorkoutSet.set_number)
    )
    rows = result.fetchall()

    return [
        {
            "id": str(row.WorkoutSet.id),
            "exercise_id": str(row.WorkoutSet.exercise_id),
            "exercise_name": row.name,
            "muscle": row.primary_muscle,
            "set_number": row.WorkoutSet.set_number,
            "planned_reps": row.WorkoutSet.planned_reps,
            "planned_weight_kg": float(row.WorkoutSet.planned_weight_kg) if row.WorkoutSet.planned_weight_kg else None,
            "actual_reps": row.WorkoutSet.actual_reps,
            "actual_weight_kg": float(row.WorkoutSet.actual_weight_kg) if row.WorkoutSet.actual_weight_kg else None,
            "rpe": row.WorkoutSet.rpe,
            "estimated_1rm": round(estimate_1rm(float(row.WorkoutSet.actual_weight_kg), row.WorkoutSet.actual_reps), 1)
                if row.WorkoutSet.actual_weight_kg and row.WorkoutSet.actual_reps else None,
        }
        for row in rows
    ]


@router.get("/sessions/{session_id}/suggest")
async def get_progressive_overload_suggestion(
    session_id: str,
    exercise_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Get a progressive overload suggestion for an exercise in this session.

    Looks at the last 3-5 sessions of this exercise and recommends
    weight, reps, and sets using the double progression method.
    """
    user = await _get_user(current_user.sub, db)

    # Get last 5 sessions' sets for this exercise
    result = await db.execute(
        select(WorkoutSet, WorkoutSession.scheduled_date)
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .where(
            WorkoutSet.exercise_id == uuid.UUID(exercise_id),
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == SessionStatus.COMPLETED,
            WorkoutSet.actual_weight_kg.isnot(None),
            WorkoutSet.actual_reps.isnot(None),
        )
        .order_by(desc(WorkoutSession.scheduled_date), WorkoutSet.set_number)
        .limit(15)
    )
    rows = result.fetchall()

    # Get exercise name
    ex_result = await db.execute(
        select(Exercise).where(Exercise.id == uuid.UUID(exercise_id))
    )
    exercise = ex_result.scalar_one_or_none()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    if not rows:
        return {
            "exercise_name": exercise.name,
            "recommended_weight_kg": 20.0,
            "recommended_sets": 3,
            "recommended_reps_min": 8,
            "recommended_reps_max": 12,
            "estimated_1rm": None,
            "rationale": "No previous data — start at 20kg and build up. Focus on perfect form.",
            "strategy": "double_progression",
        }

    set_records = [
        SetRecord(
            weight_kg=float(row.WorkoutSet.actual_weight_kg),
            reps=row.WorkoutSet.actual_reps,
            rpe=float(row.WorkoutSet.rpe) if row.WorkoutSet.rpe else None,
            is_top_set=row.WorkoutSet.set_number == 1,
        )
        for row in rows
    ]

    perf = ExercisePerformance(
        exercise_name=exercise.name,
        sets=set_records,
        target_reps_min=6 if exercise.is_compound else 8,
        target_reps_max=10 if exercise.is_compound else 15,
        strategy=ProgressionStrategy.DOUBLE_PROGRESSION,
    )

    rec = calculate_progression(perf)

    return {
        "exercise_name": rec.exercise_name,
        "recommended_weight_kg": rec.recommended_weight_kg,
        "recommended_sets": rec.recommended_sets,
        "recommended_reps_min": rec.recommended_reps_min,
        "recommended_reps_max": rec.recommended_reps_max,
        "estimated_1rm": rec.estimated_1rm_kg,
        "change_from_last": rec.change_from_last,
        "rationale": rec.rationale,
        "deload_recommended": rec.deload_recommended,
        "notes": rec.notes,
        "strategy": rec.strategy_applied.value,
    }


# ─── Plans ────────────────────────────────────────────────────────────────────

@router.get("/plans/active")
async def get_active_plan(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict | None:
    """Get the user's currently active workout plan."""
    user = await _get_user(current_user.sub, db)

    result = await db.execute(
        select(WorkoutPlan)
        .where(WorkoutPlan.user_id == user.id, WorkoutPlan.is_active.is_(True))
        .order_by(desc(WorkoutPlan.created_at))
        .limit(1)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        return None

    return {
        "id": str(plan.id),
        "name": plan.name,
        "phase": plan.phase,
        "duration_weeks": plan.duration_weeks,
        "days_per_week": plan.days_per_week,
        "start_date": plan.start_date.isoformat() if plan.start_date else None,
        "end_date": plan.end_date.isoformat() if plan.end_date else None,
    }


@router.post("/plans/generate", status_code=status.HTTP_201_CREATED)
async def generate_workout_plan(
    request: GeneratePlanRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Generate and save a new workout plan using the progressive overload engine.

    Push/Pull/Legs (5-6 days): the optimal split for intermediate lifters
    targeting V-taper, bigger arms, and fat loss simultaneously.
    """
    user = await _get_user(current_user.sub, db)

    # Deactivate any existing active plan
    existing_result = await db.execute(
        select(WorkoutPlan).where(
            WorkoutPlan.user_id == user.id, WorkoutPlan.is_active.is_(True)
        )
    )
    for existing in existing_result.scalars().all():
        existing.is_active = False

    # Generate the plan structure
    if request.plan_type == "ppl":
        plan_name = f"Push/Pull/Legs — {request.goal.title()} Phase"
        phase = "hypertrophy" if request.goal == "hypertrophy" else "fat_loss"

        push = generate_push_session()
        pull = generate_pull_session()
        legs = generate_legs_session()

        sessions_template = [
            ("Push A", ["chest", "front_deltoid", "side_deltoid", "triceps"], push),
            ("Pull A", ["lats", "mid_back", "rear_deltoid", "biceps"], pull),
            ("Legs A", ["quads", "hamstrings", "glutes", "calves"], legs),
            ("Push B", ["chest", "front_deltoid", "side_deltoid", "triceps"], push),
            ("Pull B", ["lats", "mid_back", "rear_deltoid", "biceps"], pull),
        ]
    else:
        raise HTTPException(status_code=400, detail="Unsupported plan type. Use 'ppl'.")

    # Create the plan record
    plan = WorkoutPlan(
        user_id=user.id,
        name=plan_name,
        description=f"AI-generated {request.plan_type.upper()} program for {request.goal}",
        phase=phase,
        duration_weeks=8,
        days_per_week=request.days_per_week,
        start_date=date.today(),
        is_active=True,
    )
    db.add(plan)
    await db.flush()

    # Get exercise IDs from DB for the exercises used in the plan
    exercise_names = list({ex.name for day in sessions_template for ex in day[2]})
    ex_result = await db.execute(
        select(Exercise).where(Exercise.name.in_(exercise_names))
    )
    exercise_map = {e.name: e for e in ex_result.scalars().all()}

    # Create one sample week of sessions (starting today)
    from datetime import timedelta
    today = date.today()
    weekday = today.weekday()  # 0=Monday
    # Start on next Monday
    days_to_monday = (7 - weekday) % 7
    week_start = today + timedelta(days=days_to_monday or 7)

    # Map PPL to Mon-Fri schedule
    session_dates = [
        week_start,                        # Monday: Push A
        week_start + timedelta(days=1),    # Tuesday: Pull A
        week_start + timedelta(days=2),    # Wednesday: Legs A
        week_start + timedelta(days=3),    # Thursday: Push B
        week_start + timedelta(days=4),    # Friday: Pull B
    ]

    created_sessions = []
    for i, (name, muscles, exercises) in enumerate(sessions_template[:request.days_per_week]):
        session = WorkoutSession(
            plan_id=plan.id,
            user_id=user.id,
            session_name=name,
            scheduled_date=session_dates[i],
            muscle_groups_targeted=muscles,
            status=SessionStatus.SCHEDULED,
        )
        db.add(session)
        await db.flush()

        # Pre-populate planned sets
        for ex_slot in exercises:
            exercise = exercise_map.get(ex_slot.name)
            if not exercise:
                continue
            for set_num in range(1, ex_slot.sets + 1):
                ws = WorkoutSet(
                    session_id=session.id,
                    exercise_id=exercise.id,
                    set_number=set_num,
                    planned_reps=ex_slot.reps_min,
                    planned_weight_kg=ex_slot.suggested_weight_kg,
                )
                db.add(ws)

        created_sessions.append({"name": name, "date": session_dates[i].isoformat(), "exercises": len(exercises)})

    await db.commit()
    logger.info("Generated new workout plan", user_id=current_user.sub, plan=plan_name)

    return {
        "plan_id": str(plan.id),
        "plan_name": plan_name,
        "phase": phase,
        "days_per_week": request.days_per_week,
        "duration_weeks": 8,
        "week_1_sessions": created_sessions,
        "message": "Plan generated. First week sessions are scheduled and ready to log.",
    }
