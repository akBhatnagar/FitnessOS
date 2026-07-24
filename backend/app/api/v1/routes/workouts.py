"""
Workout Tracker API — full CRUD for sessions, sets, and exercise library.

Endpoints:
- GET  /workouts/exercises         — search exercise library
- GET  /workouts/exercises/:id     — exercise detail + history + 1RM
- GET  /workouts/sessions/today    — today's sessions
- GET  /workouts/sessions/history  — recent session history
- POST /workouts/sessions          — create a new session
- POST /workouts/sessions/generate — create session with personalized exercises
- POST /workouts/sessions/:id/start    — mark session started
- POST /workouts/sessions/:id/complete — complete session + log all sets
- POST /workouts/sessions/:id/sets     — add/update a set live
- GET  /workouts/sessions/:id/suggest  — progressive overload suggestion for this session
- GET  /workouts/plans/active          — active workout plan
- POST /workouts/plans/generate        — generate a new Push/Pull/Legs plan
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import today_in_timezone
from app.core.logging import get_logger
from app.core.security import TokenPayload, get_current_user
from app.db.models.user import User
from app.db.models.workout import Exercise, SessionStatus, WorkoutPlan, WorkoutSession, WorkoutSet
from app.db.session import get_db
from app.services.training.progressive_overload import (
    ExercisePerformance,
    ExerciseSlot,
    ProgressionStrategy,
    SetRecord,
    calculate_progression,
    estimate_1rm,
)
from app.services.training.personalized_generator import (
    TrainingGoal,
    alternatives_with_prescriptions,
    generate_personalized_session,
    load_training_context,
    plan_summary,
    session_type_from_name,
    slots_to_plan_exercises,
)
from app.services.training.ai_plan_generator import (
    enrich_entries_with_alternatives,
    generate_ai_muscle_plan,
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


class CreateExerciseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    primary_muscle: str = Field(min_length=1, max_length=50)
    is_compound: bool = False


class GeneratePlanRequest(BaseModel):
    plan_type: str = Field("ppl", description="ppl (Push/Pull/Legs), upper_lower, full_body")
    days_per_week: int = Field(5, ge=3, le=6)
    goal: str = Field("hypertrophy", description="hypertrophy, strength, fat_loss")
    start_date: date | None = Field(None, description="First session date, defaults to today")


class GenerateSessionRequest(BaseModel):
    session_name: str = Field(min_length=1, max_length=255)
    scheduled_date: date
    muscle_groups: list[str] = []
    generation_type: str = Field(
        "muscle",
        description="push, pull, legs, muscle, mixed",
    )
    goal: str | None = None
    auto_start: bool = False


class PreviewSessionRequest(BaseModel):
    session_name: str = Field(min_length=1, max_length=255)
    muscle_groups: list[str] = []
    generation_type: str = Field("muscle", description="push, pull, legs, muscle, mixed")
    goal: str | None = None
    exclude_exercise_ids: list[str] = []


class PlanSetEntry(BaseModel):
    set_number: int = Field(ge=1, le=20)
    weight_kg: float = Field(ge=0, le=500)
    reps: int = Field(ge=1, le=100)


class PlanExerciseEntry(BaseModel):
    exercise_id: str
    sets: list[PlanSetEntry] = Field(min_length=1)


class SavePlanRequest(BaseModel):
    session_name: str = Field(min_length=1, max_length=255)
    scheduled_date: date
    muscle_groups: list[str] = []
    exercises: list[PlanExerciseEntry] = Field(min_length=1)
    session_id: str | None = None
    start_workout: bool = False


class WorkoutSetActual(BaseModel):
    exercise_id: str
    set_number: int = Field(ge=1, le=20)
    actual_weight_kg: float = Field(ge=0, le=500)
    actual_reps: int = Field(ge=1, le=100)


class SaveWorkoutRequest(BaseModel):
    sets: list[WorkoutSetActual] = Field(min_length=1)


# ─── Helper — resolve user ────────────────────────────────────────────────────

async def _get_user(clerk_id: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _user_today(user: User) -> date:
    return today_in_timezone(user.timezone)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")
    return slug[:200] or "exercise"


async def _populate_planned_sets(
    db: AsyncSession,
    session: WorkoutSession,
    slots: list[ExerciseSlot],
    exercise_map: dict[str, Exercise],
) -> int:
    """Pre-populate planned sets for a session. Returns exercise count."""
    count = 0
    for ex_slot in slots:
        exercise = exercise_map.get(ex_slot.name)
        if not exercise:
            continue
        count += 1
        for set_num in range(1, ex_slot.sets + 1):
            db.add(
                WorkoutSet(
                    session_id=session.id,
                    exercise_id=exercise.id,
                    set_number=set_num,
                    planned_reps=ex_slot.reps_min,
                    planned_weight_kg=ex_slot.suggested_weight_kg,
                )
            )
    return count


async def _build_session_plan_entries(
    db: AsyncSession,
    user: User,
    session_name: str,
    generation_type: str,
    muscle_groups: list[str],
    goal: str | None,
    exclude_exercise_ids: list[str] | None = None,
) -> tuple[list[dict], object]:
    """Generate plan entries via AI (muscle/mixed) with rule-engine fallback."""
    gen_type = generation_type
    if gen_type == "muscle" and session_name:
        inferred = session_type_from_name(session_name)
        if inferred in ("push", "pull", "legs", "mixed"):
            gen_type = inferred

    ctx = await load_training_context(db, user, goal or "fat_loss")
    all_exercises = list((await db.execute(select(Exercise))).scalars().all())
    exercise_by_name = {e.name: e for e in all_exercises}
    exercise_by_id = {str(e.id): e for e in all_exercises}
    exclude = set(exclude_exercise_ids or [])

    entries: list[dict] | None = None
    if gen_type in ("muscle", "mixed"):
        n_muscles = len(muscle_groups or [])
        if gen_type == "mixed":
            target = 6
        elif n_muscles >= 6:
            target = 7
        elif n_muscles >= 3:
            target = 6
        else:
            target = 5
        entries = await generate_ai_muscle_plan(
            session_name=session_name,
            muscle_groups=muscle_groups or [],
            ctx=ctx,
            all_exercises=all_exercises,
            exclude_exercise_ids=exclude,
            target_exercises=target,
        )

    if not entries:
        slots = generate_personalized_session(
            gen_type,
            ctx,
            all_exercises,
            muscle_groups=muscle_groups or None,
            exclude_exercise_ids=exclude,
        )
        entries = slots_to_plan_exercises(slots, exercise_by_name)
        entries = enrich_entries_with_alternatives(
            entries,
            exercise_by_id=exercise_by_id,
            all_exercises=all_exercises,
            ctx=ctx,
        )

    return entries, ctx


async def _generate_plan_slots(
    db: AsyncSession,
    user: User,
    session_name: str,
    generation_type: str,
    muscle_groups: list[str],
    goal: str | None,
    exclude_exercise_ids: list[str] | None = None,
):
    gen_type = generation_type
    if gen_type == "muscle" and session_name:
        inferred = session_type_from_name(session_name)
        if inferred in ("push", "pull", "legs", "mixed"):
            gen_type = inferred

    ctx = await load_training_context(db, user, goal or "fat_loss")
    all_exercises = list((await db.execute(select(Exercise))).scalars().all())
    exercise_map = {e.name: e for e in all_exercises}
    exclude = set(exclude_exercise_ids or [])

    slots = generate_personalized_session(
        gen_type,
        ctx,
        all_exercises,
        muscle_groups=muscle_groups or None,
        exclude_exercise_ids=exclude,
    )
    return ctx, slots, exercise_map, all_exercises


def _plan_entries_to_response(
    entries: list[dict],
    session_name: str,
    personalization: list[str] | None = None,
    goal: str | None = None,
    session_id: str | None = None,
) -> dict:
    summary = plan_summary(entries)
    return {
        "session_id": session_id,
        "session_name": session_name,
        "exercises": entries,
        "summary": summary,
        "personalization": personalization or [],
        "goal": goal,
    }


async def _load_session_plan_rows(db: AsyncSession, session_id: uuid.UUID) -> list:
    result = await db.execute(
        select(WorkoutSet, Exercise)
        .join(Exercise, WorkoutSet.exercise_id == Exercise.id)
        .where(WorkoutSet.session_id == session_id)
        .order_by(WorkoutSet.created_at, WorkoutSet.set_number)
    )
    return result.fetchall()


def _rows_to_plan_entries(rows: list) -> list[dict]:
    """Group DB set rows into plan exercise entries preserving order."""
    order: list[str] = []
    grouped: dict[str, dict] = {}

    for row in rows:
        ws, exercise = row.WorkoutSet, row.Exercise
        ex_id = str(exercise.id)
        if ex_id not in grouped:
            order.append(ex_id)
            grouped[ex_id] = {
                "exercise_id": ex_id,
                "name": exercise.name,
                "primary_muscle": exercise.primary_muscle,
                "is_compound": exercise.is_compound,
                "tips": exercise.tips,
                "sets": [],
            }
        entry = {
            "set_number": ws.set_number,
            "weight_kg": float(ws.planned_weight_kg) if ws.planned_weight_kg is not None else (
                float(ws.actual_weight_kg) if ws.actual_weight_kg is not None else 0.0
            ),
            "reps": ws.planned_reps or ws.actual_reps or 10,
        }
        if ws.actual_weight_kg is not None:
            entry["actual_weight_kg"] = float(ws.actual_weight_kg)
        if ws.actual_reps is not None:
            entry["actual_reps"] = ws.actual_reps
        grouped[ex_id]["sets"].append(entry)

    for ex_id in order:
        grouped[ex_id]["sets"].sort(key=lambda s: s["set_number"])

    return [grouped[ex_id] for ex_id in order]


async def _replace_session_plan(
    db: AsyncSession,
    session: WorkoutSession,
    exercises: list[PlanExerciseEntry],
) -> None:
    """Replace planned sets on a session, preserving logged actuals where possible."""
    existing_result = await db.execute(
        select(WorkoutSet).where(WorkoutSet.session_id == session.id)
    )
    existing = existing_result.scalars().all()
    actuals: dict[tuple[str, int], WorkoutSet] = {}
    for ws in existing:
        if ws.actual_weight_kg is not None or ws.actual_reps is not None:
            actuals[(str(ws.exercise_id), ws.set_number)] = ws

    await db.execute(delete(WorkoutSet).where(WorkoutSet.session_id == session.id))
    await db.flush()

    for ex_entry in exercises:
        ex_uuid = uuid.UUID(ex_entry.exercise_id)
        for s in ex_entry.sets:
            key = (ex_entry.exercise_id, s.set_number)
            prev = actuals.get(key)
            db.add(
                WorkoutSet(
                    session_id=session.id,
                    exercise_id=ex_uuid,
                    set_number=s.set_number,
                    planned_reps=s.reps,
                    planned_weight_kg=s.weight_kg,
                    actual_reps=prev.actual_reps if prev else None,
                    actual_weight_kg=float(prev.actual_weight_kg) if prev and prev.actual_weight_kg else None,
                    rpe=prev.rpe if prev else None,
                )
            )


def _exercise_to_dict(exercise: Exercise) -> dict:
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
    }


# ─── Exercise Library ────────────────────────────────────────────────────────

@router.get("/exercises")
async def search_exercises(
    query: str = "",
    muscle_group: str | None = None,
    muscle_groups: str | None = Query(None, description="Comma-separated primary muscles"),
    tag: str | None = None,
    modality: str | None = Query(None, description="gym (strength only) | swimming | all"),
    limit: int = Query(60, le=200),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Search the exercise library with optional filters."""
    stmt = select(Exercise)
    if query:
        stmt = stmt.where(Exercise.name.ilike(f"%{query}%"))
    if muscle_group:
        stmt = stmt.where(Exercise.primary_muscle == muscle_group)
    if muscle_groups:
        muscles = [m.strip() for m in muscle_groups.split(",") if m.strip()]
        if muscles:
            stmt = stmt.where(Exercise.primary_muscle.in_(muscles))
    if tag:
        stmt = stmt.where(Exercise.tags.any(tag))
    if modality == "gym":
        # Keep swimming / pure cardio out of gym workout builders
        stmt = stmt.where(
            ~Exercise.exercise_type.in_(["swimming", "cardio"]),
            ~Exercise.tags.any("swimming"),
            ~Exercise.tags.any("hiit"),
        )
    elif modality == "swimming":
        stmt = stmt.where(
            (Exercise.exercise_type == "swimming") | Exercise.tags.any("swimming")
        )
    stmt = stmt.order_by(Exercise.name).limit(limit)

    result = await db.execute(stmt)
    exercises = result.scalars().all()

    return [_exercise_to_dict(e) for e in exercises]


@router.post("/exercises", status_code=status.HTTP_201_CREATED)
async def create_exercise(
    request: CreateExerciseRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a custom exercise and add it to the library."""
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Exercise name is required")

    existing_result = await db.execute(
        select(Exercise).where(func.lower(Exercise.name) == name.lower())
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return _exercise_to_dict(existing)

    base_slug = _slugify(name)
    slug = base_slug
    slug_result = await db.execute(select(Exercise).where(Exercise.slug == slug))
    if slug_result.scalar_one_or_none():
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"

    exercise = Exercise(
        name=name,
        slug=slug,
        exercise_type="strength",
        primary_muscle=request.primary_muscle,
        secondary_muscles=[],
        equipment_needed=[],
        is_compound=request.is_compound,
        tags=["custom"],
    )
    db.add(exercise)
    await db.flush()
    await db.commit()

    return _exercise_to_dict(exercise)


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


@router.get("/exercises/{exercise_id}/alternatives")
async def get_exercise_alternatives(
    exercise_id: str,
    exclude_ids: str = Query("", description="Comma-separated exercise IDs to exclude"),
    limit: int = Query(5, ge=1, le=10),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    Intelligent alternative exercises for swapping in a workout plan.

    Matches by modality (strength/cardio/swimming), movement pattern, and muscle.
    Each alternative includes a personalized sets/weight/reps prescription.
    """
    user = await _get_user(current_user.sub, db)

    ex_result = await db.execute(
        select(Exercise).where(Exercise.id == uuid.UUID(exercise_id))
    )
    exercise = ex_result.scalar_one_or_none()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    ctx = await load_training_context(db, user, "fat_loss")
    all_exercises = list((await db.execute(select(Exercise))).scalars().all())
    exclude = {e.strip() for e in exclude_ids.split(",") if e.strip()}

    pairs = alternatives_with_prescriptions(
        exercise, all_exercises, ctx, exclude, limit=limit,
    )
    return [
        {
            **_exercise_to_dict(alt),
            "prescription": {
                "sets": slot.sets,
                "reps_min": slot.reps_min,
                "reps_max": slot.reps_max,
                "weight_kg": slot.suggested_weight_kg,
                "notes": slot.notes,
                "set_plan": [
                    {
                        "set_number": n,
                        "weight_kg": slot.suggested_weight_kg,
                        "reps": slot.reps_min,
                    }
                    for n in range(1, slot.sets + 1)
                ],
            },
        }
        for alt, slot in pairs
    ]


# ─── Sessions ─────────────────────────────────────────────────────────────────

@router.get("/sessions/today")
async def get_todays_sessions(
    date_param: Optional[date] = Query(None, alias="date", description="YYYY-MM-DD, defaults to today"),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Scheduled workout sessions for a given day (defaults to today)."""
    user = await _get_user(current_user.sub, db)
    user_today = _user_today(user)
    target_date = date_param or user_today
    if target_date > user_today:
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
    """Recent workouts the user actually logged or is doing — not future AI filler."""
    user = await _get_user(current_user.sub, db)
    user_today = _user_today(user)

    result = await db.execute(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.scheduled_date <= user_today,
            WorkoutSession.status.in_([
                SessionStatus.COMPLETED,
                SessionStatus.IN_PROGRESS,
                SessionStatus.SCHEDULED,
            ]),
        )
        .order_by(desc(WorkoutSession.scheduled_date), desc(WorkoutSession.created_at))
        .limit(min(limit * 3, 80))
    )
    sessions = result.scalars().all()

    output = []
    for s in sessions:
        actual_count = await db.execute(
            select(func.count()).select_from(WorkoutSet).where(
                WorkoutSet.session_id == s.id,
                WorkoutSet.actual_weight_kg.isnot(None),
                WorkoutSet.actual_reps.isnot(None),
            )
        )
        sets_logged = actual_count.scalar_one()

        # Hide unused AI-generated PPL fillers the user never started
        is_ai_ppl = bool(
            s.plan_id
            and s.session_name in {"Push A", "Pull A", "Legs A", "Push B", "Pull B"}
        )
        if is_ai_ppl and s.status == SessionStatus.SCHEDULED and sets_logged == 0:
            continue
        if s.status == SessionStatus.SCHEDULED and sets_logged == 0 and s.scheduled_date < user_today:
            # Past scheduled never started — don't clutter recent list
            continue

        output.append({
            "id": str(s.id),
            "session_name": s.session_name,
            "date": s.scheduled_date.isoformat(),
            "scheduled_date": s.scheduled_date.isoformat(),
            "status": s.status,
            "duration_minutes": s.duration_minutes,
            "muscle_groups": s.muscle_groups_targeted,
            "sets_logged": sets_logged,
            "effort_rating": s.effort_rating,
            "fatigue_rating": s.fatigue_rating,
        })
        if len(output) >= min(limit, 50):
            break
    return output


PPL_AI_SESSION_NAMES = {"Push A", "Pull A", "Legs A", "Push B", "Pull B"}


async def _cleanup_unused_ai_ppl_sessions(db: AsyncSession, user: User) -> int:
    """Delete AI-generated PPL sessions that were never started/logged."""
    result = await db.execute(
        select(WorkoutSession).where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == SessionStatus.SCHEDULED,
            WorkoutSession.plan_id.isnot(None),
            WorkoutSession.session_name.in_(PPL_AI_SESSION_NAMES),
        )
    )
    sessions = list(result.scalars().all())
    deleted = 0
    for s in sessions:
        actuals = await db.execute(
            select(func.count()).select_from(WorkoutSet).where(
                WorkoutSet.session_id == s.id,
                WorkoutSet.actual_weight_kg.isnot(None),
            )
        )
        if actuals.scalar_one() == 0:
            await db.delete(s)
            deleted += 1
    if deleted:
        await db.flush()
    return deleted


@router.post("/plans/cleanup-unused")
async def cleanup_unused_plans(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove unused AI-generated Push/Pull/Legs sessions the user never logged."""
    user = await _get_user(current_user.sub, db)
    deleted = await _cleanup_unused_ai_ppl_sessions(db, user)
    await db.commit()
    return {"deleted": deleted, "message": f"Removed {deleted} unused AI plan sessions"}


@router.post("/sessions/preview")
async def preview_session_plan(
    request: PreviewSessionRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Preview a personalized workout plan without saving to the database."""
    user = await _get_user(current_user.sub, db)

    entries, ctx = await _build_session_plan_entries(
        db,
        user,
        request.session_name,
        request.generation_type,
        request.muscle_groups,
        request.goal,
        request.exclude_exercise_ids,
    )
    if not entries:
        raise HTTPException(status_code=400, detail="Could not generate exercises for this session")

    return _plan_entries_to_response(
        entries,
        request.session_name,
        ctx.personalization_notes,
        ctx.goal.value,
    )


@router.get("/sessions/{session_id}/plan")
async def get_session_plan(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Load the editable plan for an existing session."""
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

    rows = await _load_session_plan_rows(db, session.id)
    entries = _rows_to_plan_entries(rows)

    # Attach load display metadata + fresh alternatives for Alt button
    if entries:
        ctx = await load_training_context(db, user, "fat_loss")
        all_exercises = list((await db.execute(select(Exercise))).scalars().all())
        exercise_by_id = {str(e.id): e for e in all_exercises}
        entries = enrich_entries_with_alternatives(
            entries,
            exercise_by_id=exercise_by_id,
            all_exercises=all_exercises,
            ctx=ctx,
        )

    return _plan_entries_to_response(
        entries,
        session.session_name,
        session_id=str(session.id),
    )


@router.post("/sessions/save-plan", status_code=status.HTTP_201_CREATED)
async def save_session_plan(
    request: SavePlanRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Save or update a workout plan (scheduled). Optionally start the workout."""
    user = await _get_user(current_user.sub, db)

    if request.scheduled_date > _user_today(user):
        raise HTTPException(status_code=400, detail="Cannot schedule workouts for future dates")

    if request.session_id:
        result = await db.execute(
            select(WorkoutSession).where(
                WorkoutSession.id == uuid.UUID(request.session_id),
                WorkoutSession.user_id == user.id,
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session.session_name = request.session_name
        session.muscle_groups_targeted = request.muscle_groups
    else:
        session = WorkoutSession(
            user_id=user.id,
            session_name=request.session_name,
            scheduled_date=request.scheduled_date,
            muscle_groups_targeted=request.muscle_groups,
            status=SessionStatus.SCHEDULED,
        )
        db.add(session)
        await db.flush()

    await _replace_session_plan(db, session, request.exercises)

    if request.start_workout:
        session.status = SessionStatus.IN_PROGRESS
        session.started_at = datetime.now(timezone.utc)
    elif session.status != SessionStatus.IN_PROGRESS:
        session.status = SessionStatus.SCHEDULED

    await db.commit()

    entries = _rows_to_plan_entries(await _load_session_plan_rows(db, session.id))
    return {
        "id": str(session.id),
        "session_name": session.session_name,
        "status": session.status,
        "scheduled_date": session.scheduled_date.isoformat(),
        "muscle_groups": session.muscle_groups_targeted,
        "exercises": entries,
        "summary": plan_summary(entries),
    }


@router.post("/sessions/generate", status_code=status.HTTP_201_CREATED)
async def generate_personalized_session_endpoint(
    request: GenerateSessionRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Create a workout session with exercises and weights personalized to the user.

    Uses AI for muscle-targeted sessions (with rule-engine fallback), plus
    body weight, goals, history, and preferences.
    """
    user = await _get_user(current_user.sub, db)

    if request.scheduled_date > _user_today(user):
        raise HTTPException(status_code=400, detail="Cannot schedule workouts for future dates")

    entries, ctx = await _build_session_plan_entries(
        db,
        user,
        request.session_name,
        request.generation_type,
        request.muscle_groups,
        request.goal,
    )

    if not entries:
        raise HTTPException(status_code=400, detail="Could not generate exercises for this session")

    session = WorkoutSession(
        user_id=user.id,
        session_name=request.session_name,
        scheduled_date=request.scheduled_date,
        muscle_groups_targeted=request.muscle_groups,
        status=SessionStatus.IN_PROGRESS if request.auto_start else SessionStatus.SCHEDULED,
        started_at=datetime.now(timezone.utc) if request.auto_start else None,
    )
    db.add(session)
    await db.flush()

    plan_entries = [
        PlanExerciseEntry(
            exercise_id=e["exercise_id"],
            sets=[
                PlanSetEntry(
                    set_number=s["set_number"],
                    weight_kg=float(s.get("weight_kg") or 0),
                    reps=int(s.get("reps") or 10),
                )
                for s in e.get("sets", [])
            ],
        )
        for e in entries
        if e.get("sets")
    ]
    await _replace_session_plan(db, session, plan_entries)
    await db.commit()

    return {
        "id": str(session.id),
        "session_name": session.session_name,
        "status": session.status,
        "exercises": entries,
        "exercise_count": len(entries),
        "summary": plan_summary(entries),
        "personalization": ctx.personalization_notes,
        "goal": ctx.goal.value,
    }


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually create a workout session."""
    user = await _get_user(current_user.sub, db)

    if request.scheduled_date > _user_today(user):
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


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_session(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a workout session and all its sets."""
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

    await db.delete(session)
    await db.commit()
    logger.info("Deleted workout session", session_id=session_id, user_id=current_user.sub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.post("/sessions/{session_id}/save-workout")
async def save_workout(
    session_id: str,
    request: SaveWorkoutRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Save all logged sets from a workout and mark the session complete."""
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

    if session.status == SessionStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Session already completed")

    if not session.started_at:
        session.started_at = datetime.now(timezone.utc)
        session.status = SessionStatus.IN_PROGRESS

    for entry in request.sets:
        existing_result = await db.execute(
            select(WorkoutSet).where(
                WorkoutSet.session_id == session.id,
                WorkoutSet.exercise_id == uuid.UUID(entry.exercise_id),
                WorkoutSet.set_number == entry.set_number,
            )
        )
        workout_set = existing_result.scalar_one_or_none()
        if workout_set:
            workout_set.actual_weight_kg = entry.actual_weight_kg
            workout_set.actual_reps = entry.actual_reps
        else:
            db.add(
                WorkoutSet(
                    session_id=session.id,
                    exercise_id=uuid.UUID(entry.exercise_id),
                    set_number=entry.set_number,
                    actual_weight_kg=entry.actual_weight_kg,
                    actual_reps=entry.actual_reps,
                )
            )

    now = datetime.now(timezone.utc)
    session.status = SessionStatus.COMPLETED
    session.completed_at = now
    if session.started_at:
        session.duration_minutes = (now - session.started_at).seconds // 60

    await db.commit()

    return {
        "status": "completed",
        "sets_saved": len(request.sets),
        "duration_minutes": session.duration_minutes,
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

    # Remove unused AI filler sessions from previous generates
    await _cleanup_unused_ai_ppl_sessions(db, user)

    # Deactivate any existing active plan
    existing_result = await db.execute(
        select(WorkoutPlan).where(
            WorkoutPlan.user_id == user.id, WorkoutPlan.is_active.is_(True)
        )
    )
    for existing in existing_result.scalars().all():
        existing.is_active = False

    if request.plan_type != "ppl":
        raise HTTPException(status_code=400, detail="Unsupported plan type. Use 'ppl'.")

    ctx = await load_training_context(db, user, request.goal)
    all_exercises = list((await db.execute(select(Exercise))).scalars().all())
    exercise_map = {e.name: e for e in all_exercises}

    goal_label = ctx.goal.value.replace("_", " ").title()
    plan_name = f"Push/Pull/Legs — {goal_label} Phase"
    phase = (
        "hypertrophy" if ctx.goal == TrainingGoal.HYPERTROPHY
        else "strength" if ctx.goal == TrainingGoal.STRENGTH
        else "cutting"
    )

    sessions_template = [
        ("Push A", ["chest", "front_deltoid", "side_deltoid", "triceps"], "push"),
        ("Pull A", ["lats", "mid_back", "rear_deltoid", "biceps"], "pull"),
        ("Legs A", ["quads", "hamstrings", "glutes", "calves"], "legs"),
        ("Push B", ["chest", "front_deltoid", "side_deltoid", "triceps"], "push"),
        ("Pull B", ["lats", "mid_back", "rear_deltoid", "biceps"], "pull"),
    ]

    from datetime import timedelta

    week_start = request.start_date or _user_today(user)
    if week_start > _user_today(user):
        raise HTTPException(status_code=400, detail="Cannot schedule plans for future dates")

    # Only schedule TODAY's session in the calendar — keep the rest as plan blueprint
    # so Recent Workouts isn't flooded with unused Push B / Pull B fillers.
    today_slot = sessions_template[0]
    week_blueprint = [
        {
            "name": name,
            "muscles": muscles,
            "split": split,
            "day_offset": i,
        }
        for i, (name, muscles, split) in enumerate(sessions_template[:request.days_per_week])
    ]

    plan = WorkoutPlan(
        user_id=user.id,
        name=plan_name,
        description=f"Personalized {request.plan_type.upper()} program ({ctx.goal.value})",
        phase=phase,
        duration_weeks=8,
        days_per_week=request.days_per_week,
        start_date=week_start,
        is_active=True,
        plan_metadata={
            "personalization": ctx.personalization_notes,
            "weight_kg": ctx.weight_kg,
            "week_blueprint": week_blueprint,
        },
    )
    db.add(plan)
    await db.flush()

    name, muscles, split_type = today_slot
    slots = generate_personalized_session(
        split_type,
        ctx,
        all_exercises,
        muscle_groups=muscles,
    )

    session = WorkoutSession(
        plan_id=plan.id,
        user_id=user.id,
        session_name=name,
        scheduled_date=week_start,
        muscle_groups_targeted=muscles,
        status=SessionStatus.SCHEDULED,
    )
    db.add(session)
    await db.flush()

    ex_count = await _populate_planned_sets(db, session, slots, exercise_map)
    created_sessions = [{
        "id": str(session.id),
        "name": name,
        "date": week_start.isoformat(),
        "muscle_groups": muscles,
        "exercises": ex_count,
        "exercise_names": [s.name for s in slots],
    }]

    await db.commit()
    logger.info("Generated personalized workout plan", user_id=current_user.sub, plan=plan_name)

    return {
        "plan_id": str(plan.id),
        "plan_name": plan_name,
        "phase": phase,
        "goal": ctx.goal.value,
        "days_per_week": request.days_per_week,
        "duration_weeks": 8,
        "week_1_sessions": created_sessions,
        "personalization": ctx.personalization_notes,
        "message": "Personalized plan generated. Today's session is ready to review — swimming is kept separate.",
    }
