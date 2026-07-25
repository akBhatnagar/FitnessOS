"""
Personalized workout generation.

Selects exercises and loads based on:
- User weight, activity level, and active goals (especially fat loss)
- Logged workout history (frequency, progressive overload)
- Preferred / disliked exercises and injuries
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.goal import Goal, GoalCategory, GoalStatus
from app.db.models.user import ActivityLevel, User, UserPreferences
from app.db.models.workout import Exercise, SessionStatus, WorkoutSession, WorkoutSet
from app.services.training.progressive_overload import (
    ExercisePerformance,
    ExerciseSlot,
    ProgressionStrategy,
    SetRecord,
    calculate_progression,
    estimate_1rm,
    percentage_of_1rm,
)


class TrainingGoal(str, Enum):
    FAT_LOSS = "fat_loss"
    HYPERTROPHY = "hypertrophy"
    STRENGTH = "strength"


@dataclass
class ExerciseHistoryStats:
    exercise_id: str
    exercise_name: str
    set_count: int
    best_weight_kg: float
    best_reps: int
    estimated_1rm: float
    recent_sets: list[SetRecord] = field(default_factory=list)


@dataclass
class UserTrainingContext:
    user_id: uuid.UUID
    weight_kg: float
    target_weight_kg: float | None
    activity_level: ActivityLevel
    goal: TrainingGoal
    preferred: list[str]
    disliked: list[str]
    injuries: list[str]
    exercise_stats: dict[str, ExerciseHistoryStats]
    anchor_1rms: dict[str, float]
    personalization_notes: list[str] = field(default_factory=list)


@dataclass
class GoalParams:
    compound_reps: tuple[int, int]
    isolation_reps: tuple[int, int]
    compound_intensity_pct: float
    isolation_intensity_pct: float
    compound_rest: int
    isolation_rest: int
    compound_sets: int
    isolation_sets: int


@dataclass
class SlotSpec:
    primary_muscles: list[str]
    role: str  # main_compound | secondary_compound | isolation
    prefer_compound: bool
    sets: int | None = None


PUSH_SLOTS = [
    SlotSpec(["chest"], "main_compound", True, 4),
    SlotSpec(["front_deltoid"], "secondary_compound", True, 3),
    SlotSpec(["chest"], "isolation", False, 3),
    SlotSpec(["side_deltoid"], "isolation", False, 4),
    SlotSpec(["triceps"], "isolation", False, 3),
    SlotSpec(["triceps"], "isolation", False, 3),
]

PULL_SLOTS = [
    SlotSpec(["lats", "mid_back", "lower_back"], "main_compound", True, 3),
    SlotSpec(["lats"], "secondary_compound", True, 4),
    SlotSpec(["mid_back", "lats"], "secondary_compound", True, 4),
    SlotSpec(["mid_back"], "isolation", False, 3),
    SlotSpec(["rear_deltoid"], "isolation", False, 3),
    SlotSpec(["biceps"], "isolation", False, 3),
    SlotSpec(["biceps", "brachialis"], "isolation", False, 3),
]

LEGS_SLOTS = [
    SlotSpec(["quads"], "main_compound", True, 4),
    SlotSpec(["hamstrings", "glutes"], "secondary_compound", True, 3),
    SlotSpec(["quads"], "isolation", False, 3),
    SlotSpec(["quads", "glutes"], "isolation", False, 3),
    SlotSpec(["hamstrings"], "isolation", False, 3),
    SlotSpec(["calves"], "isolation", False, 4),
]

SESSION_TYPE_SLOTS: dict[str, list[SlotSpec]] = {
    "push": PUSH_SLOTS,
    "pull": PULL_SLOTS,
    "legs": LEGS_SLOTS,
}

ACTIVITY_MULTIPLIER: dict[str, float] = {
    "sedentary": 0.70,
    "lightly_active": 0.85,
    "moderately_active": 1.0,
    "very_active": 1.10,
    "extra_active": 1.20,
}


def _goal_params(goal: TrainingGoal) -> GoalParams:
    if goal == TrainingGoal.FAT_LOSS:
        return GoalParams(
            compound_reps=(8, 12),
            isolation_reps=(12, 18),
            compound_intensity_pct=68,
            isolation_intensity_pct=62,
            compound_rest=90,
            isolation_rest=60,
            compound_sets=3,
            isolation_sets=3,
        )
    if goal == TrainingGoal.STRENGTH:
        return GoalParams(
            compound_reps=(4, 6),
            isolation_reps=(8, 10),
            compound_intensity_pct=82,
            isolation_intensity_pct=72,
            compound_rest=240,
            isolation_rest=90,
            compound_sets=4,
            isolation_sets=3,
        )
    return GoalParams(
        compound_reps=(6, 10),
        isolation_reps=(10, 15),
        compound_intensity_pct=75,
        isolation_intensity_pct=70,
        compound_rest=150,
        isolation_rest=75,
        compound_sets=4,
        isolation_sets=3,
    )


def _resolve_goal(request_goal: str, goals: list[Goal], prefs: UserPreferences | None) -> TrainingGoal:
    if request_goal in {g.value for g in TrainingGoal}:
        return TrainingGoal(request_goal)

    for g in sorted(goals, key=lambda x: -x.priority):
        if g.category == GoalCategory.FAT_LOSS:
            return TrainingGoal.FAT_LOSS
        if g.category == GoalCategory.STRENGTH:
            return TrainingGoal.STRENGTH
        if g.category in (GoalCategory.MUSCLE_GAIN, GoalCategory.AESTHETICS):
            return TrainingGoal.HYPERTROPHY

    if prefs and prefs.current_weight_kg and prefs.target_weight_kg:
        if float(prefs.target_weight_kg) < float(prefs.current_weight_kg) - 1:
            return TrainingGoal.FAT_LOSS

    return TrainingGoal.HYPERTROPHY


def _estimate_anchor_1rms(weight_kg: float, activity: ActivityLevel | str) -> dict[str, float]:
    act_key = activity.value if hasattr(activity, "value") else str(activity)
    mult = ACTIVITY_MULTIPLIER.get(act_key, 1.0)
    w = max(weight_kg, 50.0)
    return {
        "bench": round(w * 0.85 * mult / 2.5) * 2.5,
        "ohp": round(w * 0.55 * mult / 2.5) * 2.5,
        "row": round(w * 0.75 * mult / 2.5) * 2.5,
        "deadlift": round(w * 1.35 * mult / 2.5) * 2.5,
        "squat": round(w * 1.10 * mult / 2.5) * 2.5,
        "rdl": round(w * 0.95 * mult / 2.5) * 2.5,
    }


def _anchor_for_muscle(primary_muscle: str, anchors: dict[str, float]) -> float:
    mapping = {
        "chest": ("bench", 0.75),
        "front_deltoid": ("ohp", 0.75),
        "side_deltoid": ("ohp", 0.25),
        "rear_deltoid": ("row", 0.20),
        "triceps": ("bench", 0.30),
        "lats": ("row", 0.80),
        "mid_back": ("row", 0.75),
        "lower_back": ("deadlift", 0.65),
        "biceps": ("row", 0.35),
        "brachialis": ("row", 0.30),
        "quads": ("squat", 0.77),
        "hamstrings": ("rdl", 0.72),
        "glutes": ("rdl", 0.70),
        "calves": ("squat", 0.50),
        "abs": ("bench", 0.15),
        "core": ("bench", 0.15),
    }
    key, pct = mapping.get(primary_muscle, ("row", 0.50))
    return anchors[key] * (pct / 0.75)


def _matches_disliked(exercise: Exercise, disliked: list[str]) -> bool:
    name = exercise.name.lower()
    tags = [t.lower() for t in (exercise.tags or [])]
    for term in disliked:
        t = term.lower().strip()
        if not t:
            continue
        if t in name or any(t in tag for tag in tags):
            return True
        if t == "compound lifts" and exercise.is_compound:
            return False
        if t == "compound" and exercise.is_compound and "dislike_compound" in t:
            return True
    return False


def _matches_injury(exercise: Exercise, injuries: list[str]) -> bool:
    if not injuries:
        return False
    name = exercise.name.lower()
    injury_blocks = {
        "lower back": ["deadlift", "good morning", "back extension"],
        "knee": ["squat", "lunge", "leg press", "leg extension"],
        "shoulder": ["overhead press", "ohp", "upright row"],
    }
    for injury in injuries:
        il = injury.lower()
        for key, blocked in injury_blocks.items():
            if key in il and any(b in name for b in blocked):
                return True
    return False


def _score_exercise(
    exercise: Exercise,
    ctx: UserTrainingContext,
    slot: SlotSpec,
    exclude_ids: set[str],
) -> float:
    if str(exercise.id) in exclude_ids:
        return -999.0
    if _matches_disliked(exercise, ctx.disliked):
        return -999.0
    if _matches_injury(exercise, ctx.injuries):
        return -999.0

    score = 0.0
    stats = ctx.exercise_stats.get(str(exercise.id))

    if stats:
        score += min(45.0, stats.set_count * 1.5)
        score += 25.0  # familiarity — prefer exercises you've done before

    for pref in ctx.preferred:
        pl = pref.lower()
        if pl in exercise.name.lower():
            score += 35.0
        elif pl in [t.lower() for t in (exercise.tags or [])]:
            score += 25.0
        elif pl == "compound lifts" and exercise.is_compound:
            score += 30.0

    if ctx.goal == TrainingGoal.FAT_LOSS:
        if "fat_loss" in (exercise.tags or []):
            score += 20.0
        if slot.role == "isolation":
            score += 8.0
    if "priority" in (exercise.tags or []):
        score += 12.0
    if "v_taper" in (exercise.tags or []) and ctx.goal == TrainingGoal.FAT_LOSS:
        score += 10.0

    if slot.prefer_compound and exercise.is_compound:
        score += 28.0
    elif not slot.prefer_compound and not exercise.is_compound:
        score += 18.0

    if exercise.primary_muscle in slot.primary_muscles:
        score += 30.0
    elif any(sm in slot.primary_muscles for sm in (exercise.secondary_muscles or [])):
        score += 12.0

    return score


def _pick_exercise(
    candidates: list[Exercise],
    ctx: UserTrainingContext,
    slot: SlotSpec,
    exclude_ids: set[str],
) -> Exercise | None:
    scored = [(ex, _score_exercise(ex, ctx, slot, exclude_ids)) for ex in candidates]
    scored = [(ex, s) for ex, s in scored if s > 0]
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[1], x[0].name))
    return scored[0][0]


def _build_slot(
    exercise: Exercise,
    ctx: UserTrainingContext,
    params: GoalParams,
    slot: SlotSpec,
) -> ExerciseSlot:
    modality = _exercise_modality(exercise)

    # Cardio / swimming: time/effort-based, not barbell loads
    if modality in ("cardio", "swimming"):
        return ExerciseSlot(
            name=exercise.name,
            sets=slot.sets or 4,
            reps_min=8 if modality == "swimming" else 12,
            reps_max=12 if modality == "swimming" else 20,
            suggested_weight_kg=0.0,
            rest_seconds=60 if "hiit" in (exercise.name.lower() + " ".join(exercise.tags or [])) else 90,
            notes=(
                "Intervals / cardio — treat reps as work units (laps or bursts). "
                "Adjust effort to RPE 7–8."
                if modality == "swimming" or "hiit" in exercise.name.lower()
                else "Bodyweight / cardio work — focus on quality and pace."
            ),
            strategy=ProgressionStrategy.DOUBLE_PROGRESSION,
        )

    is_compound = exercise.is_compound or slot.prefer_compound
    reps_min, reps_max = params.compound_reps if is_compound else params.isolation_reps
    sets = slot.sets or (params.compound_sets if is_compound else params.isolation_sets)
    rest = params.compound_rest if is_compound else params.isolation_rest
    intensity = params.compound_intensity_pct if is_compound else params.isolation_intensity_pct
    strategy = ProgressionStrategy.LINEAR if slot.role == "main_compound" else ProgressionStrategy.DOUBLE_PROGRESSION

    stats = ctx.exercise_stats.get(str(exercise.id))
    if stats and stats.recent_sets:
        perf = ExercisePerformance(
            exercise_name=exercise.name,
            sets=stats.recent_sets,
            target_reps_min=reps_min,
            target_reps_max=reps_max,
            strategy=strategy,
            total_sessions=max(1, stats.set_count // 3),
        )
        rec = calculate_progression(perf)
        note = rec.rationale
        if rec.deload_recommended:
            note = f"Deload week: {rec.rationale}"
        return ExerciseSlot(
            name=exercise.name,
            sets=rec.recommended_sets,
            reps_min=rec.recommended_reps_min,
            reps_max=rec.recommended_reps_max,
            suggested_weight_kg=rec.recommended_weight_kg,
            rest_seconds=rest,
            notes=note,
            strategy=strategy,
        )

    anchor = _anchor_for_muscle(exercise.primary_muscle, ctx.anchor_1rms)
    weight = max(2.5, percentage_of_1rm(anchor, intensity))
    return ExerciseSlot(
        name=exercise.name,
        sets=sets,
        reps_min=reps_min,
        reps_max=reps_max,
        suggested_weight_kg=weight,
        rest_seconds=rest,
        notes=f"Starting weight based on your {ctx.weight_kg:.0f}kg profile — adjust as needed.",
        strategy=strategy,
    )


async def load_training_context(
    db: AsyncSession,
    user: User,
    request_goal: str = "fat_loss",
) -> UserTrainingContext:
    prefs_result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    prefs = prefs_result.scalar_one_or_none()

    goals_result = await db.execute(
        select(Goal).where(
            Goal.user_id == user.id,
            Goal.status == GoalStatus.ACTIVE,
        )
    )
    goals = list(goals_result.scalars().all())

    weight = 75.0
    target_weight = None
    activity = ActivityLevel.MODERATELY_ACTIVE
    preferred: list[str] = []
    disliked: list[str] = []
    injuries: list[str] = []

    if prefs:
        if prefs.current_weight_kg:
            weight = float(prefs.current_weight_kg)
        if prefs.target_weight_kg:
            target_weight = float(prefs.target_weight_kg)
        activity = prefs.activity_level or ActivityLevel.MODERATELY_ACTIVE
        preferred = list(prefs.preferred_exercises or [])
        disliked = list(prefs.disliked_exercises or [])
        injuries = list(prefs.current_injuries or [])

    # Swimming prefs belong to the Swimming module — ignore for gym generation
    preferred = [
        p for p in preferred
        if p.lower().strip() not in {"swimming", "swim", "hiit", "cardio"}
    ]

    goal = _resolve_goal(request_goal, goals, prefs)
    anchors = _estimate_anchor_1rms(weight, activity)

    # Load per-exercise history
    hist_result = await db.execute(
        select(
            Exercise.id,
            Exercise.name,
            func.count(WorkoutSet.id).label("set_count"),
            func.max(WorkoutSet.actual_weight_kg).label("best_weight"),
        )
        .join(WorkoutSet, WorkoutSet.exercise_id == Exercise.id)
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user.id,
            WorkoutSession.status == SessionStatus.COMPLETED,
            WorkoutSet.actual_weight_kg.isnot(None),
            WorkoutSet.actual_reps.isnot(None),
        )
        .group_by(Exercise.id, Exercise.name)
    )
    exercise_stats: dict[str, ExerciseHistoryStats] = {}

    for row in hist_result.fetchall():
        ex_id = str(row.id)
        # Fetch recent sets for progression
        sets_result = await db.execute(
            select(WorkoutSet)
            .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
            .where(
                WorkoutSet.exercise_id == row.id,
                WorkoutSession.user_id == user.id,
                WorkoutSession.status == SessionStatus.COMPLETED,
                WorkoutSet.actual_weight_kg.isnot(None),
                WorkoutSet.actual_reps.isnot(None),
            )
            .order_by(desc(WorkoutSession.scheduled_date), WorkoutSet.set_number)
            .limit(12)
        )
        recent = [
            SetRecord(
                weight_kg=float(s.actual_weight_kg),
                reps=s.actual_reps,
                rpe=float(s.rpe) if s.rpe else None,
                is_top_set=s.set_number == 1,
            )
            for s in sets_result.scalars().all()
        ]
        best_w = float(row.best_weight)
        best_reps = max((s.reps for s in recent if s.weight_kg == best_w), default=8)
        exercise_stats[ex_id] = ExerciseHistoryStats(
            exercise_id=ex_id,
            exercise_name=row.name,
            set_count=int(row.set_count),
            best_weight_kg=best_w,
            best_reps=best_reps,
            estimated_1rm=estimate_1rm(best_w, best_reps),
            recent_sets=list(reversed(recent)),
        )

        # Refine anchor 1RMs from actual compound performance
        name_l = row.name.lower()
        est = exercise_stats[ex_id].estimated_1rm
        if "bench press" in name_l and "incline" not in name_l:
            anchors["bench"] = max(anchors["bench"], est)
        elif "squat" in name_l and "split" not in name_l:
            anchors["squat"] = max(anchors["squat"], est)
        elif "deadlift" in name_l:
            anchors["deadlift"] = max(anchors["deadlift"], est)
        elif "overhead press" in name_l or name_l.startswith("ohp"):
            anchors["ohp"] = max(anchors["ohp"], est)
        elif "row" in name_l:
            anchors["row"] = max(anchors["row"], est)

    # Learn dislikes: exercises planned but never logged, plus modalities the user never trains
    inferred = await _infer_disliked_from_history(db, user.id, exercise_stats)
    for term in inferred:
        if term.lower() not in {d.lower() for d in disliked}:
            disliked.append(term)

    # Persist learned dislikes so they stick across regenerations
    if prefs is not None and inferred:
        merged = list(dict.fromkeys([*(prefs.disliked_exercises or []), *inferred]))
        if merged != list(prefs.disliked_exercises or []):
            prefs.disliked_exercises = merged

    notes: list[str] = []
    if exercise_stats:
        top = sorted(exercise_stats.values(), key=lambda x: -x.set_count)[:3]
        names = ", ".join(s.exercise_name for s in top)
        notes.append(f"Prioritized exercises you've logged before: {names}")
    if inferred:
        notes.append(f"Avoiding based on your history: {', '.join(inferred[:4])}")
    if goal == TrainingGoal.FAT_LOSS:
        notes.append(f"Fat loss focus: higher reps, moderate weight (~{weight:.0f}kg profile)")
        if target_weight:
            notes.append(f"Target weight: {target_weight:.0f}kg")
    elif exercise_stats:
        notes.append("Progressive overload applied from your recent sessions")

    return UserTrainingContext(
        user_id=user.id,
        weight_kg=weight,
        target_weight_kg=target_weight,
        activity_level=activity,
        goal=goal,
        preferred=preferred,
        disliked=disliked,
        injuries=injuries,
        exercise_stats=exercise_stats,
        anchor_1rms=anchors,
        personalization_notes=notes,
    )


async def _infer_disliked_from_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    exercise_stats: dict[str, ExerciseHistoryStats],
) -> list[str]:
    """Infer exercises/modalities the user consistently skips or never logs."""
    inferred: list[str] = []

    # Exercises that were planned but never actually logged
    planned_result = await db.execute(
        select(Exercise.id, Exercise.name, Exercise.tags, Exercise.exercise_type)
        .join(WorkoutSet, WorkoutSet.exercise_id == Exercise.id)
        .join(WorkoutSession, WorkoutSet.session_id == WorkoutSession.id)
        .where(
            WorkoutSession.user_id == user_id,
            WorkoutSet.planned_weight_kg.isnot(None),
        )
        .group_by(Exercise.id, Exercise.name, Exercise.tags, Exercise.exercise_type)
    )
    for row in planned_result.fetchall():
        ex_id = str(row.id)
        if ex_id in exercise_stats:
            continue
        name_l = row.name.lower()
        tags = [t.lower() for t in (row.tags or [])]
        etype = (row.exercise_type or "").lower()
        if (
            "hiit" in name_l or "hiit" in tags
            or etype in ("swimming", "cardio")
            or "swimming" in tags
            or "cardio" in tags
        ):
            if "hiit" in name_l or "hiit" in tags:
                inferred.append("hiit")
            if etype == "swimming" or "swimming" in tags:
                inferred.append("swimming")
            # Also dislike this specific exercise name for stronger matching
            inferred.append(row.name)

    # If user has gym history but never logged any HIIT/swim sets, avoid those modalities
    if exercise_stats:
        logged_names = " ".join(s.exercise_name.lower() for s in exercise_stats.values())
        if "hiit" not in logged_names and "hiit" not in {d.lower() for d in inferred}:
            inferred.append("hiit")
        if "swim" not in logged_names and "freestyle" not in logged_names:
            if "swimming" not in {d.lower() for d in inferred}:
                inferred.append("swimming")

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in inferred:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            unique.append(t)
    return unique


def _muscle_slots(muscle_groups: list[str], mixed: bool = False) -> list[SlotSpec]:
    if mixed:
        return [
            SlotSpec(muscle_groups, "main_compound", True, 3),
            SlotSpec(muscle_groups, "secondary_compound", True, 3),
            SlotSpec(muscle_groups, "isolation", False, 3),
            SlotSpec(muscle_groups, "isolation", False, 3),
            SlotSpec(muscle_groups, "isolation", False, 3),
        ]
    return [
        SlotSpec(muscle_groups, "main_compound", True, 4),
        SlotSpec(muscle_groups, "secondary_compound", True, 3),
        SlotSpec(muscle_groups, "isolation", False, 3),
        SlotSpec(muscle_groups, "isolation", False, 3),
    ]


def generate_personalized_session(
    session_type: str,
    ctx: UserTrainingContext,
    all_exercises: list[Exercise],
    muscle_groups: list[str] | None = None,
    exclude_exercise_ids: set[str] | None = None,
) -> list[ExerciseSlot]:
    """Build a personalized gym session as a list of ExerciseSlots.

    Swimming / cardio modalities are excluded — those belong to the Swimming module.
    """
    exclude = exclude_exercise_ids or set()
    params = _goal_params(ctx.goal)

    # Gym plans use strength exercises only
    gym_exercises = [
        ex for ex in all_exercises
        if _exercise_modality(ex) == "strength"
    ]

    if session_type in ("push", "pull", "legs"):
        slots = SESSION_TYPE_SLOTS[session_type]
    elif session_type == "mixed":
        muscles = muscle_groups or [
            "chest", "lats", "quads", "front_deltoid", "biceps", "triceps",
        ]
        slots = _muscle_slots(muscles, mixed=True)
    else:
        muscles = muscle_groups or ["chest"]
        slots = _muscle_slots(muscles, mixed=False)

    result: list[ExerciseSlot] = []
    used_ids: set[str] = set(exclude)

    for slot in slots:
        # Muscle/mixed sessions: primary muscle only — no secondary leakage (bench≠arms)
        if session_type in ("muscle", "mixed"):
            candidates = [
                ex for ex in gym_exercises
                if ex.primary_muscle in slot.primary_muscles
            ]
        else:
            candidates = [
                ex for ex in gym_exercises
                if ex.primary_muscle in slot.primary_muscles
                or any(sm in slot.primary_muscles for sm in (ex.secondary_muscles or []))
            ]
        if slot.prefer_compound:
            compounds = [ex for ex in candidates if ex.is_compound]
            if compounds:
                candidates = compounds

        picked = _pick_exercise(candidates, ctx, slot, used_ids)
        if not picked:
            # Soft fallback: same primary muscles only (never the whole gym library)
            loose = [
                ex for ex in gym_exercises
                if ex.primary_muscle in slot.primary_muscles
            ]
            picked = _pick_exercise(loose or candidates, ctx, slot, used_ids)

        if picked:
            used_ids.add(str(picked.id))
            result.append(_build_slot(picked, ctx, params, slot))

    return result


def session_type_from_name(session_name: str) -> str | None:
    n = session_name.lower().strip()
    if n == "mixed workout":
        return "mixed"
    # Combo sessions like "Back + Biceps" stay muscle-targeted
    if " + " in n or " and " in n:
        return "muscle"
    if n == "push day" or n.startswith("push "):
        return "push"
    if n == "pull day" or n.startswith("pull "):
        return "pull"
    if n == "legs day" or n.startswith("leg"):
        return "legs"
    return "muscle"


def slots_to_plan_exercises(
    slots: list[ExerciseSlot],
    exercise_map: dict[str, Exercise],
) -> list[dict]:
    """Convert ExerciseSlots to API plan exercise entries."""
    entries: list[dict] = []
    for slot in slots:
        exercise = exercise_map.get(slot.name)
        if not exercise:
            continue
        entries.append({
            "exercise_id": str(exercise.id),
            "name": exercise.name,
            "primary_muscle": exercise.primary_muscle,
            "is_compound": exercise.is_compound,
            "tips": exercise.tips,
            "notes": slot.notes,
            "sets": [
                {
                    "set_number": n,
                    "weight_kg": slot.suggested_weight_kg,
                    "reps": slot.reps_min,
                }
                for n in range(1, slot.sets + 1)
            ],
        })
    return entries


def plan_summary(exercises: list[dict]) -> dict:
    total_sets = sum(len(ex.get("sets", [])) for ex in exercises)
    return {"exercises": len(exercises), "sets": total_sets}


# Movement / modality families used for intelligent swap matching
_MOVEMENT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("horizontal_push", ("bench", "chest press", "push-up", "push up", "flye", "chest fly")),
    ("incline_push", ("incline",)),
    ("overhead_press", ("overhead press", "shoulder press", "ohp")),
    ("lateral_raise", ("lateral raise", "side raise")),
    ("rear_delt", ("face pull", "rear delt", "reverse fly")),
    ("vertical_pull", ("pull-up", "chin-up", "lat pulldown", "pulldown")),
    ("horizontal_pull", ("row", "meadows")),
    ("hip_hinge", ("deadlift", "rdl", "romanian", "good morning", "hip thrust")),
    ("squat_pattern", ("squat", "leg press", "lunge", "split squat", "step-up")),
    ("knee_flexion", ("leg curl", "hamstring curl")),
    ("knee_extension", ("leg extension",)),
    ("calf", ("calf raise",)),
    ("elbow_extension", ("pushdown", "tricep", "skull crusher", "overhead extension")),
    ("elbow_flexion", ("curl", "hammer")),
    ("core", ("plank", "crunch", "sit-up", "leg raise", "ab wheel")),
    ("swim_hiit", ("hiit", "interval", "freestyle", "swim")),
    ("swim_technique", ("drill", "kick", "pull buoy")),
    ("cardio", ("burpee", "jump rope", "row erg", "bike", "run", "sprint")),
]


def _keyword_matches(keyword: str, text: str) -> bool:
    """Whole-word / phrase match so 'fly' does not match 'freestyle'."""
    k = keyword.lower().strip()
    t = text.lower()
    if not k:
        return False
    if " " in k or "-" in k:
        return k in t
    # Word boundary match for single tokens
    return re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", t) is not None


def _exercise_modality(exercise: Exercise) -> str:
    """High-level modality: strength | cardio | swimming."""
    tags = {t.lower() for t in (exercise.tags or [])}
    etype = (exercise.exercise_type or "").lower()
    name = exercise.name.lower()

    if etype in ("swimming",) or "swimming" in tags or "swim" in name:
        return "swimming"
    if (
        etype in ("cardio", "plyometric")
        or "cardio" in tags
        or "hiit" in tags
        or "hiit" in name
    ):
        return "cardio"
    return "strength"


def _movement_patterns(exercise: Exercise) -> set[str]:
    name = exercise.name.lower()
    tags = [t.lower() for t in (exercise.tags or [])]
    tag_blob = " ".join(tags)
    patterns: set[str] = set()
    for pattern, keywords in _MOVEMENT_PATTERNS:
        if any(_keyword_matches(k, name) or _keyword_matches(k, tag_blob) for k in keywords):
            patterns.add(pattern)
    if not patterns:
        # Fall back to coarse muscle-family patterns
        muscle = exercise.primary_muscle
        if muscle in ("chest",):
            patterns.add("horizontal_push")
        elif muscle in ("front_deltoid",):
            patterns.add("overhead_press")
        elif muscle in ("side_deltoid",):
            patterns.add("lateral_raise")
        elif muscle in ("rear_deltoid",):
            patterns.add("rear_delt")
        elif muscle in ("lats",):
            patterns.add("vertical_pull")
        elif muscle in ("mid_back", "lower_back"):
            patterns.add("horizontal_pull")
        elif muscle in ("quads",):
            patterns.add("squat_pattern")
        elif muscle in ("hamstrings", "glutes"):
            patterns.add("hip_hinge")
        elif muscle in ("calves",):
            patterns.add("calf")
        elif muscle in ("biceps", "brachialis"):
            patterns.add("elbow_flexion")
        elif muscle in ("triceps",):
            patterns.add("elbow_extension")
        elif muscle in ("abs", "core"):
            patterns.add("core")
    return patterns


def _slot_for_exercise(exercise: Exercise) -> SlotSpec:
    modality = _exercise_modality(exercise)
    if modality != "strength":
        return SlotSpec(
            primary_muscles=[exercise.primary_muscle],
            role="isolation",
            prefer_compound=False,
            sets=3,
        )
    return SlotSpec(
        primary_muscles=[exercise.primary_muscle],
        role="main_compound" if exercise.is_compound else "isolation",
        prefer_compound=exercise.is_compound,
        sets=4 if exercise.is_compound else 3,
    )


def find_exercise_alternatives(
    exercise: Exercise,
    all_exercises: list[Exercise],
    ctx: UserTrainingContext,
    exclude_ids: set[str],
    limit: int = 5,
) -> list[Exercise]:
    """
    Find intelligent swap alternatives.

    Prefer same modality (strength/cardio/swimming), same movement pattern,
    overlapping tags, and same primary muscle. Strongly reject mismatched
    modalities (e.g. dumbbell row is not an alternative to HIIT).
    """
    source_modality = _exercise_modality(exercise)
    source_patterns = _movement_patterns(exercise)
    source_tags = {t.lower() for t in (exercise.tags or [])}
    exclude = set(exclude_ids) | {str(exercise.id)}
    slot = _slot_for_exercise(exercise)

    scored: list[tuple[Exercise, float]] = []
    for ex in all_exercises:
        if str(ex.id) in exclude:
            continue
        if _matches_disliked(ex, ctx.disliked) or _matches_injury(ex, ctx.injuries):
            continue

        cand_modality = _exercise_modality(ex)
        # Hard rule: never cross modalities
        if cand_modality != source_modality:
            continue

        # Muscle: primary match preferred; secondary only within same modality
        muscle_ok = (
            ex.primary_muscle == exercise.primary_muscle
            or any(sm == exercise.primary_muscle for sm in (ex.secondary_muscles or []))
            or any(sm == ex.primary_muscle for sm in (exercise.secondary_muscles or []))
        )
        cand_patterns = _movement_patterns(ex)
        pattern_overlap = source_patterns & cand_patterns
        cand_tags = {t.lower() for t in (ex.tags or [])}
        tag_overlap = source_tags & cand_tags - {"priority", "v_taper", "fat_loss"}

        # For swimming/cardio, tag/pattern match is required (muscle alone is not enough)
        if source_modality in ("swimming", "cardio"):
            if not pattern_overlap and not tag_overlap:
                continue
        elif not muscle_ok and not pattern_overlap:
            continue

        score = 0.0
        if pattern_overlap:
            score += 60.0 + 10.0 * len(pattern_overlap)
        if muscle_ok and ex.primary_muscle == exercise.primary_muscle:
            score += 35.0
        elif muscle_ok:
            score += 12.0
        if tag_overlap:
            score += 15.0 * len(tag_overlap)
        if ex.is_compound == exercise.is_compound:
            score += 15.0
        else:
            score -= 8.0

        # Prefer familiar exercises, but less so than movement match
        stats = ctx.exercise_stats.get(str(ex.id))
        if stats:
            score += min(20.0, stats.set_count)

        # Slight preference for same equipment family via tags
        if "bodyweight" in source_tags and "bodyweight" in cand_tags:
            score += 10.0
        if "cable" in " ".join(source_tags) and "cable" in " ".join(cand_tags):
            score += 8.0

        # Base gym-quality score (soft)
        base = _score_exercise(ex, ctx, slot, exclude)
        if base > 0:
            score += min(25.0, base * 0.25)

        if score >= 40.0:  # require a meaningful match
            scored.append((ex, score))

    scored.sort(key=lambda x: (-x[1], x[0].name))
    return [ex for ex, _ in scored[:limit]]


def prescribe_for_exercise(
    exercise: Exercise,
    ctx: UserTrainingContext,
) -> ExerciseSlot:
    """Build a personalized set/rep/weight prescription for one exercise."""
    slot = _slot_for_exercise(exercise)
    params = _goal_params(ctx.goal)
    return _build_slot(exercise, ctx, params, slot)


def alternatives_with_prescriptions(
    exercise: Exercise,
    all_exercises: list[Exercise],
    ctx: UserTrainingContext,
    exclude_ids: set[str],
    limit: int = 5,
) -> list[tuple[Exercise, ExerciseSlot]]:
    """Alternatives plus personalized loads for each."""
    alts = find_exercise_alternatives(exercise, all_exercises, ctx, exclude_ids, limit=limit)
    return [(alt, prescribe_for_exercise(alt, ctx)) for alt in alts]
