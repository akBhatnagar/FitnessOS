"""Rich context and dynamic prompt building for AI muscle workout generation."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.measurement import Measurement
from app.db.models.user import User, UserPreferences
from app.db.models.workout import Exercise, SessionStatus, WorkoutSession, WorkoutSet
from app.services.training.personalized_generator import ExerciseHistoryStats, UserTrainingContext


@dataclass
class BodyProfile:
    height_cm: float | None = None
    weight_kg: float | None = None
    target_weight_kg: float | None = None
    latest_measurement: dict[str, Any] = field(default_factory=dict)
    measurement_trend: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SessionExerciseLog:
    exercise_id: str
    exercise_name: str
    primary_muscle: str
    secondary_muscles: list[str]
    sets: list[dict[str, Any]]


@dataclass
class MuscleSessionSnapshot:
    session_id: str
    session_name: str
    scheduled_date: str
    muscle_groups_targeted: list[str]
    exercises: list[SessionExerciseLog]


@dataclass
class MusclePlanPromptContext:
    body: BodyProfile
    same_muscle_sessions: list[MuscleSessionSnapshot]
    muscle_exercise_history: list[dict[str, Any]]


def _float_val(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _measurement_payload(m: Measurement) -> dict[str, Any]:
    payload: dict[str, Any] = {"measured_on": m.measured_on.isoformat()}
    for key in (
        "weight_kg",
        "body_fat_pct",
        "muscle_mass_kg",
        "water_pct",
        "waist_cm",
        "chest_cm",
        "hips_cm",
        "shoulders_cm",
        "left_bicep_cm",
        "right_bicep_cm",
        "left_thigh_cm",
        "right_thigh_cm",
        "neck_cm",
    ):
        val = getattr(m, key, None)
        if val is not None:
            payload[key] = float(val)
    for key in ("energy_level", "sleep_quality", "stress_level", "pain_level"):
        val = getattr(m, key, None)
        if val is not None:
            payload[key] = int(val)
    if m.pain_location:
        payload["pain_location"] = m.pain_location
    return payload


async def load_body_profile(db: AsyncSession, user: User, ctx: UserTrainingContext) -> BodyProfile:
    prefs_result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    prefs = prefs_result.scalar_one_or_none()

    height = _float_val(prefs.height_cm) if prefs else None
    weight = ctx.weight_kg
    target = ctx.target_weight_kg

    meas_result = await db.execute(
        select(Measurement)
        .where(Measurement.user_id == user.id)
        .order_by(desc(Measurement.measured_on))
        .limit(5)
    )
    measurements = list(meas_result.scalars().all())

    latest = _measurement_payload(measurements[0]) if measurements else {}
    trend = [
        {
            "measured_on": m.measured_on.isoformat(),
            "weight_kg": _float_val(m.weight_kg),
            "body_fat_pct": _float_val(m.body_fat_pct),
            "waist_cm": _float_val(m.waist_cm),
        }
        for m in measurements[:3]
    ]

    return BodyProfile(
        height_cm=height,
        weight_kg=weight,
        target_weight_kg=target,
        latest_measurement=latest,
        measurement_trend=trend,
    )


async def load_same_muscle_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    muscle_groups: list[str],
    *,
    limit: int = 3,
) -> list[MuscleSessionSnapshot]:
    """Completed sessions whose targeted muscles overlap the requested groups."""
    if not muscle_groups:
        return []

    sessions_result = await db.execute(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSession.status == SessionStatus.COMPLETED,
            WorkoutSession.muscle_groups_targeted.overlap(muscle_groups),
        )
        .options(selectinload(WorkoutSession.sets).selectinload(WorkoutSet.exercise))
        .order_by(desc(WorkoutSession.scheduled_date))
        .limit(limit)
    )
    sessions = list(sessions_result.scalars().all())
    snapshots: list[MuscleSessionSnapshot] = []

    for session in sessions:
        by_exercise: dict[str, SessionExerciseLog] = {}
        for ws in sorted(session.sets, key=lambda s: (str(s.exercise_id), s.set_number)):
            if ws.actual_reps is None:
                continue
            ex = ws.exercise
            if not ex:
                continue
            eid = str(ex.id)
            if eid not in by_exercise:
                by_exercise[eid] = SessionExerciseLog(
                    exercise_id=eid,
                    exercise_name=ex.name,
                    primary_muscle=ex.primary_muscle,
                    secondary_muscles=list(ex.secondary_muscles or [])[:4],
                    sets=[],
                )
            weight = float(ws.actual_weight_kg) if ws.actual_weight_kg is not None else 0.0
            by_exercise[eid].sets.append(
                {
                    "set_number": ws.set_number,
                    "weight_kg": weight,
                    "reps": ws.actual_reps,
                    "rpe": int(ws.rpe) if ws.rpe else None,
                }
            )

        if not by_exercise:
            continue

        snapshots.append(
            MuscleSessionSnapshot(
                session_id=str(session.id),
                session_name=session.session_name,
                scheduled_date=session.scheduled_date.isoformat(),
                muscle_groups_targeted=list(session.muscle_groups_targeted or []),
                exercises=list(by_exercise.values()),
            )
        )

    return snapshots


def build_muscle_exercise_history(
    ctx: UserTrainingContext,
    muscle_groups: list[str],
    exercise_by_id: dict[str, Exercise],
) -> list[dict[str, Any]]:
    """Per-exercise performance for lifts whose primary muscle matches the target."""
    muscles = set(muscle_groups or [])
    if not muscles:
        return []

    rows: list[dict[str, Any]] = []
    for eid, stats in ctx.exercise_stats.items():
        ex = exercise_by_id.get(eid)
        if not ex or ex.primary_muscle not in muscles:
            continue
        rows.append(_serialize_exercise_history(ex, stats))

    rows.sort(key=lambda r: (-r["set_count"], r["name"]))
    return rows[:20]


def _serialize_exercise_history(ex: Exercise, stats: ExerciseHistoryStats) -> dict[str, Any]:
    recent = [
        {
            "weight_kg": s.weight_kg,
            "reps": s.reps,
            "rpe": s.rpe,
        }
        for s in stats.recent_sets[-8:]
    ]
    return {
        "exercise_id": stats.exercise_id,
        "name": stats.exercise_name,
        "primary_muscle": ex.primary_muscle,
        "secondary_muscles": list(ex.secondary_muscles or [])[:4],
        "set_count": stats.set_count,
        "best_weight_kg": stats.best_weight_kg,
        "best_reps": stats.best_reps,
        "estimated_1rm_kg": round(stats.estimated_1rm, 1),
        "recent_sets": recent,
    }


def _serialize_session_snapshot(session: MuscleSessionSnapshot) -> dict[str, Any]:
    return {
        "session_name": session.session_name,
        "date": session.scheduled_date,
        "muscle_groups": session.muscle_groups_targeted,
        "exercises": [
            {
                "exercise_id": ex.exercise_id,
                "name": ex.exercise_name,
                "primary_muscle": ex.primary_muscle,
                "logged_sets": ex.sets,
            }
            for ex in session.exercises
        ],
    }


async def build_muscle_plan_prompt_context(
    db: AsyncSession,
    user: User,
    ctx: UserTrainingContext,
    muscle_groups: list[str],
    exercise_by_id: dict[str, Exercise],
) -> MusclePlanPromptContext:
    body = await load_body_profile(db, user, ctx)
    same_muscle = await load_same_muscle_sessions(db, user.id, muscle_groups)
    history = build_muscle_exercise_history(ctx, muscle_groups, exercise_by_id)
    return MusclePlanPromptContext(
        body=body,
        same_muscle_sessions=same_muscle,
        muscle_exercise_history=history,
    )


def build_ai_muscle_prompt(
    *,
    session_name: str,
    muscle_groups: list[str],
    ctx: UserTrainingContext,
    prompt_ctx: MusclePlanPromptContext,
    catalog: list[dict[str, Any]],
    target_exercises: int,
    alternatives_per_exercise: int,
) -> tuple[str, str]:
    """Return (system_message, user_message) for the LLM."""
    body = prompt_ctx.body
    athlete = {
        "height_cm": body.height_cm,
        "weight_kg": body.weight_kg,
        "target_weight_kg": body.target_weight_kg,
        "goal": ctx.goal.value,
        "activity_level": ctx.activity_level.value if hasattr(ctx.activity_level, "value") else str(ctx.activity_level),
        "injuries_avoid": ctx.injuries or [],
        "disliked_exercises": ctx.disliked[:10] or [],
        "preferred_exercises": ctx.preferred[:10] or [],
        "latest_body_measurement": body.latest_measurement or None,
        "measurement_trend": body.measurement_trend or [],
    }

    prior_sessions = [_serialize_session_snapshot(s) for s in prompt_ctx.same_muscle_sessions]
    history = prompt_ctx.muscle_exercise_history

    system = """You are an expert strength coach building one gym workout for this athlete.

Rules:
- Choose exercises ONLY from the provided catalog (use exercise_id).
- Never invent exercises. No swimming or cardio.
- Every main exercise primary_muscle MUST be one of the requested target muscles.
- Do not pick bench press on an arms day just because triceps are secondary.
- For each main exercise, prescribe this week's sets, reps, and weight using the athlete's
  logged history and progressive overload (small increases when they hit rep targets).
- For bodyweight movements (push-ups, planks, etc.) use weight_kg: 0 for all sets.
- For dumbbells/kettlebells, weight_kg is PER HAND (each side).
- For barbells/cables/machines, weight_kg is total load on the bar/stack.
- Alternatives must train the SAME primary muscle AND the same anatomical focus
  (e.g. front deltoid vs side deltoid, lats vs mid-back, long head vs short head of biceps).
  Prefer equipment swaps (barbell → dumbbell → cable) that keep the same movement intent.
- Each alternative needs its own sets/reps/weight prescription for this week.
- Return ONLY valid JSON matching the schema exactly."""

    user = f"""Build a personalized workout for this week.

SESSION
- Name: {session_name}
- Target muscles (primary focus): {", ".join(muscle_groups) or "full gym"}

ATHLETE PROFILE
{json.dumps(athlete, indent=2)}

PRIOR SESSIONS FOR THESE MUSCLES (most recent first)
Use these to understand which exercises this athlete actually performs on {", ".join(muscle_groups)} days.
Prefer continuity with familiar lifts unless injuries/dislikes say otherwise.
{json.dumps(prior_sessions, indent=2) if prior_sessions else "[] — no prior logged sessions for these muscles yet."}

EXERCISE HISTORY ON TARGET MUSCLES (all-time logged performance)
Use weight/reps/RPE below to estimate this week's progressive overload targets.
{json.dumps(history, indent=2) if history else "[] — no logged history yet; use conservative starter loads based on bodyweight and goal."}

EXERCISE CATALOG (choose ONLY from these)
{json.dumps(catalog, indent=2)}

TASK
1. Pick {target_exercises} main exercises covering ALL target muscles (compounds first, then isolations).
2. For EACH main exercise return:
   - exercise_id from catalog
   - notes: one short coaching note (progression rationale)
   - sets: array of {{set_number, weight_kg, reps}} for this week (typically 3-4 sets)
3. For EACH main exercise return {alternatives_per_exercise} alternatives:
   - exercise_id from catalog (not duplicated in main list or other alternatives)
   - swap_reason: why it hits the same muscle region (e.g. "barbell curl → cable curl, same biceps")
   - sets: same structure with estimated loads for this week

Return JSON exactly:
{{
  "rationale": "one sentence overview",
  "exercises": [
    {{
      "exercise_id": "<catalog id>",
      "notes": "<short note>",
      "sets": [{{"set_number": 1, "weight_kg": 0, "reps": 10}}],
      "alternatives": [
        {{
          "exercise_id": "<catalog id>",
          "swap_reason": "<same muscle part explanation>",
          "sets": [{{"set_number": 1, "weight_kg": 0, "reps": 10}}]
        }}
      ]
    }}
  ]
}}"""

    return system, user
