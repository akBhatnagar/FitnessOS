"""
Progressive Overload Engine.

Implements evidence-based progression strategies:
- Epley formula for 1RM estimation
- Double progression (reps → weight)
- RIR-based auto-regulation
- Minimum Effective Dose (MED) tracking
- Deload detection and scheduling

This engine powers the Workout Agent's recommendations and ensures
training is always moving forward at a sustainable rate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─── Progression Strategies ─────────────────────────────────────────────────

class ProgressionStrategy(str, Enum):
    DOUBLE_PROGRESSION = "double_progression"   # Hit top of rep range → increase weight
    LINEAR = "linear"                           # Add fixed weight each session
    WAVE_LOADING = "wave_loading"               # 3/2/1 or 4/3/2 rep waves
    DAILY_MAX = "daily_max"                     # Work up to daily max each session
    VOLUME_ACCUMULATION = "volume_accumulation" # Add sets before adding weight
    RIR_BASED = "rir_based"                    # Reps in Reserve auto-regulation


# ─── Data Containers ─────────────────────────────────────────────────────────

@dataclass
class SetRecord:
    """A single performed set."""
    weight_kg: float
    reps: int
    rpe: float | None = None      # RPE 1-10 scale
    rir: int | None = None        # Reps in Reserve
    is_top_set: bool = False      # Is this the working set for progression?


@dataclass
class ExercisePerformance:
    """Aggregated performance for one exercise across sessions."""
    exercise_name: str
    sets: list[SetRecord]
    target_reps_min: int = 6
    target_reps_max: int = 12
    strategy: ProgressionStrategy = ProgressionStrategy.DOUBLE_PROGRESSION
    # Additional context
    weeks_at_current_weight: int = 0
    total_sessions: int = 0


@dataclass
class ProgressionRecommendation:
    """Output of the progressive overload calculation."""
    exercise_name: str
    recommended_weight_kg: float
    recommended_sets: int
    recommended_reps_min: int
    recommended_reps_max: int
    strategy_applied: ProgressionStrategy
    estimated_1rm_kg: float
    change_from_last: float          # kg change from previous session
    rationale: str
    deload_recommended: bool = False
    notes: list[str] = field(default_factory=list)


# ─── Core Formulas ───────────────────────────────────────────────────────────

def epley_1rm(weight_kg: float, reps: int) -> float:
    """
    Epley formula: 1RM = weight × (1 + reps/30)

    Most accurate for 1-10 rep range. Slightly overestimates at very high reps.
    Reference: Epley B. (1985) Poundage Chart.
    """
    if reps == 1:
        return weight_kg
    return weight_kg * (1 + reps / 30.0)


def brzycki_1rm(weight_kg: float, reps: int) -> float:
    """
    Brzycki formula: 1RM = weight / (1.0278 − 0.0278 × reps)

    More accurate for reps 1-10. Underestimates at high reps.
    Reference: Brzycki M. (1993) Strength Testing.
    """
    if reps == 1:
        return weight_kg
    denominator = 1.0278 - 0.0278 * reps
    if denominator <= 0:
        return weight_kg * (1 + reps / 30.0)  # fallback to Epley
    return weight_kg / denominator


def estimate_1rm(weight_kg: float, reps: int) -> float:
    """
    Average of Epley and Brzycki for a balanced estimate.
    Used for progression decisions and performance tracking.
    """
    return (epley_1rm(weight_kg, reps) + brzycki_1rm(weight_kg, reps)) / 2.0


def weight_for_reps(one_rm: float, target_reps: int) -> float:
    """
    Calculate load for a given rep target using the Epley inverse:
    weight = 1RM / (1 + target_reps / 30)

    Rounds to nearest 2.5kg increment (standard plate increment).
    """
    raw = one_rm / (1 + target_reps / 30.0)
    return round(raw / 2.5) * 2.5


def percentage_of_1rm(one_rm: float, percentage: float) -> float:
    """Return weight at a percentage of 1RM, rounded to 2.5kg."""
    raw = one_rm * (percentage / 100.0)
    return round(raw / 2.5) * 2.5


def rpe_to_rir(rpe: float) -> int:
    """Convert RPE (1-10) to estimated Reps in Reserve."""
    return max(0, round(10 - rpe))


def rir_to_rpe(rir: int) -> float:
    """Convert Reps in Reserve to RPE."""
    return max(1.0, 10.0 - rir)


# ─── Deload Detection ────────────────────────────────────────────────────────

def should_deload(
    sessions_at_plateau: int,
    consecutive_weeks: int,
    avg_rpe: float | None,
    weeks_since_deload: int,
) -> tuple[bool, str]:
    """
    Determine if a deload is warranted.

    Returns (should_deload, reason).

    Deload criteria (any one triggers):
    - 3+ consecutive sessions without progress (plateau)
    - 6+ weeks of consistent training without a deload
    - Average RPE consistently >= 9 for 2+ weeks (accumulated fatigue)
    """
    if sessions_at_plateau >= 3:
        return True, f"Stuck at same weight for {sessions_at_plateau} sessions — time to reset and come back stronger"

    if weeks_since_deload >= 6:
        return True, f"{weeks_since_deload} weeks without a deload — scheduled deload for recovery"

    if avg_rpe is not None and avg_rpe >= 9.0:
        return True, f"Average RPE {avg_rpe:.1f} indicates high fatigue — deload to dissipate accumulated stress"

    return False, ""


# ─── Double Progression ───────────────────────────────────────────────────────

def double_progression_next(
    last_weight_kg: float,
    last_reps: int,
    target_reps_min: int,
    target_reps_max: int,
    weight_increment_kg: float = 2.5,
) -> tuple[float, str]:
    """
    Double Progression: increase reps within a range, then increase weight.

    Logic:
    - If last_reps >= target_reps_max → increase weight, reset to target_reps_min
    - If target_reps_min <= last_reps < target_reps_max → add 1-2 reps
    - If last_reps < target_reps_min → maintain weight, focus on completing reps

    Returns (recommended_weight_kg, rationale).
    """
    if last_reps >= target_reps_max:
        new_weight = last_weight_kg + weight_increment_kg
        rationale = (
            f"Hit {last_reps} reps (top of {target_reps_min}-{target_reps_max} range) → "
            f"increase to {new_weight}kg, targeting {target_reps_min} reps"
        )
    elif last_reps >= target_reps_min:
        new_weight = last_weight_kg
        rationale = (
            f"At {last_reps} reps — within target range, keep {last_weight_kg}kg "
            f"and push for {last_reps + 1}-{last_reps + 2} reps next session"
        )
    else:
        new_weight = last_weight_kg
        rationale = (
            f"At {last_reps} reps (below target of {target_reps_min}+) — "
            f"hold {last_weight_kg}kg and aim to hit {target_reps_min} clean reps"
        )
    return new_weight, rationale


# ─── Main Calculation ────────────────────────────────────────────────────────

def calculate_progression(performance: ExercisePerformance) -> ProgressionRecommendation:
    """
    Calculate the next session's weight, sets, and reps based on recent performance.

    This is the primary function called by the Workout Agent.
    """
    sets = performance.sets
    if not sets:
        return ProgressionRecommendation(
            exercise_name=performance.exercise_name,
            recommended_weight_kg=20.0,  # safe starting weight
            recommended_sets=3,
            recommended_reps_min=performance.target_reps_min,
            recommended_reps_max=performance.target_reps_max,
            strategy_applied=performance.strategy,
            estimated_1rm_kg=0.0,
            change_from_last=0.0,
            rationale="No previous data — starting at 20kg. Focus on perfect form.",
            notes=["Start conservatively and build up over 2-3 sessions"],
        )

    # Find the best set (highest estimated 1RM)
    best_set = max(sets, key=lambda s: estimate_1rm(s.weight_kg, s.reps))
    top_set_1rm = estimate_1rm(best_set.weight_kg, best_set.reps)

    # Latest working set for progression decisions
    working_sets = [s for s in sets if s.is_top_set] or sets
    latest = working_sets[-1]

    # Average RPE for fatigue assessment
    rpe_values = [s.rpe for s in sets if s.rpe is not None]
    avg_rpe = sum(rpe_values) / len(rpe_values) if rpe_values else None

    # Deload check
    deload_needed, deload_reason = should_deload(
        sessions_at_plateau=performance.weeks_at_current_weight,
        consecutive_weeks=performance.total_sessions // 3,  # approx weeks
        avg_rpe=avg_rpe,
        weeks_since_deload=performance.total_sessions // 3,
    )

    notes: list[str] = []

    if deload_needed:
        # Deload: drop to 60% of 1RM for 2x12
        deload_weight = percentage_of_1rm(top_set_1rm, 60)
        return ProgressionRecommendation(
            exercise_name=performance.exercise_name,
            recommended_weight_kg=deload_weight,
            recommended_sets=2,
            recommended_reps_min=12,
            recommended_reps_max=15,
            strategy_applied=ProgressionStrategy.DOUBLE_PROGRESSION,
            estimated_1rm_kg=round(top_set_1rm, 1),
            change_from_last=deload_weight - latest.weight_kg,
            rationale=deload_reason,
            deload_recommended=True,
            notes=["This is a planned deload week — reduce weight but maintain volume", "Come back next week refreshed and stronger"],
        )

    if performance.strategy == ProgressionStrategy.DOUBLE_PROGRESSION:
        new_weight, rationale = double_progression_next(
            last_weight_kg=latest.weight_kg,
            last_reps=latest.reps,
            target_reps_min=performance.target_reps_min,
            target_reps_max=performance.target_reps_max,
        )

        if avg_rpe and avg_rpe >= 8.5:
            notes.append(f"RPE {avg_rpe:.1f} was high last session — consider 1 min extra rest between sets")

        return ProgressionRecommendation(
            exercise_name=performance.exercise_name,
            recommended_weight_kg=new_weight,
            recommended_sets=len(working_sets),
            recommended_reps_min=performance.target_reps_min,
            recommended_reps_max=performance.target_reps_max,
            strategy_applied=ProgressionStrategy.DOUBLE_PROGRESSION,
            estimated_1rm_kg=round(top_set_1rm, 1),
            change_from_last=new_weight - latest.weight_kg,
            rationale=rationale,
            notes=notes,
        )

    elif performance.strategy == ProgressionStrategy.LINEAR:
        increment = 2.5 if latest.weight_kg < 60 else 1.25
        new_weight = latest.weight_kg + increment
        return ProgressionRecommendation(
            exercise_name=performance.exercise_name,
            recommended_weight_kg=new_weight,
            recommended_sets=len(working_sets),
            recommended_reps_min=performance.target_reps_min,
            recommended_reps_max=performance.target_reps_max,
            strategy_applied=ProgressionStrategy.LINEAR,
            estimated_1rm_kg=round(top_set_1rm, 1),
            change_from_last=increment,
            rationale=f"Linear progression: +{increment}kg from {latest.weight_kg}kg",
            notes=notes,
        )

    elif performance.strategy == ProgressionStrategy.RIR_BASED:
        target_rir = 2  # Always leave 2 reps in tank
        current_rir = latest.rir if latest.rir is not None else rpe_to_rir(latest.rpe or 7)

        if current_rir > target_rir + 1:
            # Too easy — add weight
            new_weight = latest.weight_kg + 2.5
            rationale = f"RIR {current_rir} is above target RIR {target_rir} — increase to {new_weight}kg"
        elif current_rir < target_rir - 1:
            # Too hard — reduce weight
            new_weight = max(latest.weight_kg - 2.5, 10.0)
            rationale = f"RIR {current_rir} is below target — reduce to {new_weight}kg and build back up"
        else:
            new_weight = latest.weight_kg
            rationale = f"RIR {current_rir} is on target — maintain {latest.weight_kg}kg, push reps"

        return ProgressionRecommendation(
            exercise_name=performance.exercise_name,
            recommended_weight_kg=new_weight,
            recommended_sets=len(working_sets),
            recommended_reps_min=performance.target_reps_min,
            recommended_reps_max=performance.target_reps_max,
            strategy_applied=ProgressionStrategy.RIR_BASED,
            estimated_1rm_kg=round(top_set_1rm, 1),
            change_from_last=new_weight - latest.weight_kg,
            rationale=rationale,
            notes=notes,
        )

    # Fallback
    return ProgressionRecommendation(
        exercise_name=performance.exercise_name,
        recommended_weight_kg=latest.weight_kg,
        recommended_sets=3,
        recommended_reps_min=performance.target_reps_min,
        recommended_reps_max=performance.target_reps_max,
        strategy_applied=performance.strategy,
        estimated_1rm_kg=round(top_set_1rm, 1),
        change_from_last=0.0,
        rationale="Maintain current weight and focus on quality reps",
        notes=notes,
    )


# ─── Workout Plan Generator ──────────────────────────────────────────────────

@dataclass
class ExerciseSlot:
    """A prescribed exercise within a session."""
    name: str
    sets: int
    reps_min: int
    reps_max: int
    suggested_weight_kg: float
    rest_seconds: int
    notes: str = ""
    strategy: ProgressionStrategy = ProgressionStrategy.DOUBLE_PROGRESSION


def generate_push_session(
    bench_1rm: float = 80.0,
    ohp_1rm: float = 55.0,
    dip_1rm: float = 90.0,
) -> list[ExerciseSlot]:
    """Generate a Push (Chest/Shoulders/Triceps) session with calculated weights."""
    return [
        ExerciseSlot(
            name="Barbell Bench Press",
            sets=4,
            reps_min=6,
            reps_max=10,
            suggested_weight_kg=percentage_of_1rm(bench_1rm, 75),
            rest_seconds=180,
            notes="Main chest movement. Control the eccentric.",
        ),
        ExerciseSlot(
            name="Overhead Press (Barbell)",
            sets=3,
            reps_min=6,
            reps_max=10,
            suggested_weight_kg=percentage_of_1rm(ohp_1rm, 75),
            rest_seconds=180,
            notes="Shoulders: brace core, full lockout.",
        ),
        ExerciseSlot(
            name="Incline Dumbbell Press",
            sets=3,
            reps_min=8,
            reps_max=12,
            suggested_weight_kg=percentage_of_1rm(bench_1rm * 0.6, 70),
            rest_seconds=120,
            notes="Upper chest emphasis. Slight incline (30-45°).",
        ),
        ExerciseSlot(
            name="Lateral Raise (Dumbbell)",
            sets=4,
            reps_min=12,
            reps_max=20,
            suggested_weight_kg=max(5.0, percentage_of_1rm(ohp_1rm * 0.2, 70)),
            rest_seconds=60,
            notes="V-taper builder. Light weight, high quality. Minimal momentum.",
        ),
        ExerciseSlot(
            name="Cable Tricep Pushdown",
            sets=3,
            reps_min=10,
            reps_max=15,
            suggested_weight_kg=percentage_of_1rm(bench_1rm * 0.3, 70),
            rest_seconds=90,
            notes="Full extension. Squeeze at the bottom.",
        ),
        ExerciseSlot(
            name="Overhead Tricep Extension",
            sets=3,
            reps_min=10,
            reps_max=15,
            suggested_weight_kg=percentage_of_1rm(bench_1rm * 0.25, 70),
            rest_seconds=90,
            notes="Long head emphasis. Keep elbows tucked.",
        ),
    ]


def generate_pull_session(
    deadlift_1rm: float = 120.0,
    row_1rm: float = 80.0,
) -> list[ExerciseSlot]:
    """Generate a Pull (Back/Biceps) session."""
    return [
        ExerciseSlot(
            name="Deadlift (Conventional)",
            sets=3,
            reps_min=4,
            reps_max=6,
            suggested_weight_kg=percentage_of_1rm(deadlift_1rm, 80),
            rest_seconds=300,
            notes="Hinge from hips. Brace core hard. Neutral spine.",
            strategy=ProgressionStrategy.LINEAR,
        ),
        ExerciseSlot(
            name="Pull-up / Lat Pulldown",
            sets=4,
            reps_min=6,
            reps_max=10,
            suggested_weight_kg=percentage_of_1rm(row_1rm * 0.8, 75),
            rest_seconds=180,
            notes="Full range. Dead hang at bottom, chest to bar at top.",
        ),
        ExerciseSlot(
            name="Barbell Row (Bent-over)",
            sets=4,
            reps_min=6,
            reps_max=10,
            suggested_weight_kg=percentage_of_1rm(row_1rm, 75),
            rest_seconds=180,
            notes="Back parallel to floor. Lead with elbows.",
        ),
        ExerciseSlot(
            name="Seated Cable Row",
            sets=3,
            reps_min=10,
            reps_max=15,
            suggested_weight_kg=percentage_of_1rm(row_1rm * 0.7, 70),
            rest_seconds=90,
            notes="Mid-back. Full stretch at front, full contraction at back.",
        ),
        ExerciseSlot(
            name="Face Pull (Cable)",
            sets=3,
            reps_min=15,
            reps_max=20,
            suggested_weight_kg=percentage_of_1rm(row_1rm * 0.2, 60),
            rest_seconds=60,
            notes="Rear delts + rotator cuff. Pull to forehead.",
        ),
        ExerciseSlot(
            name="Barbell Curl",
            sets=3,
            reps_min=8,
            reps_max=12,
            suggested_weight_kg=percentage_of_1rm(row_1rm * 0.35, 70),
            rest_seconds=90,
            notes="Bicep peak builder. Full ROM, no swinging.",
        ),
        ExerciseSlot(
            name="Hammer Curl",
            sets=3,
            reps_min=10,
            reps_max=15,
            suggested_weight_kg=percentage_of_1rm(row_1rm * 0.30, 70),
            rest_seconds=90,
            notes="Brachialis + forearm. Neutral grip throughout.",
        ),
    ]


def generate_legs_session(
    squat_1rm: float = 100.0,
    rdl_1rm: float = 90.0,
) -> list[ExerciseSlot]:
    """Generate a Legs session."""
    return [
        ExerciseSlot(
            name="Barbell Squat (High-bar)",
            sets=4,
            reps_min=5,
            reps_max=8,
            suggested_weight_kg=percentage_of_1rm(squat_1rm, 77),
            rest_seconds=300,
            notes="Quad dominant. Break parallel. Knees tracking over toes.",
            strategy=ProgressionStrategy.LINEAR,
        ),
        ExerciseSlot(
            name="Romanian Deadlift (RDL)",
            sets=3,
            reps_min=8,
            reps_max=12,
            suggested_weight_kg=percentage_of_1rm(rdl_1rm, 72),
            rest_seconds=180,
            notes="Hamstring focus. Soft knee bend, hinge until mild stretch.",
        ),
        ExerciseSlot(
            name="Leg Press",
            sets=3,
            reps_min=10,
            reps_max=15,
            suggested_weight_kg=percentage_of_1rm(squat_1rm * 1.5, 70),
            rest_seconds=120,
            notes="Quad emphasis. Don't let back lift off pad.",
        ),
        ExerciseSlot(
            name="Walking Lunges",
            sets=3,
            reps_min=10,
            reps_max=14,
            suggested_weight_kg=percentage_of_1rm(squat_1rm * 0.3, 60),
            rest_seconds=90,
            notes="Per leg. Balance and quad emphasis.",
        ),
        ExerciseSlot(
            name="Leg Curl (Machine)",
            sets=3,
            reps_min=10,
            reps_max=15,
            suggested_weight_kg=percentage_of_1rm(rdl_1rm * 0.4, 65),
            rest_seconds=90,
            notes="Lying or seated. Hamstring isolation.",
        ),
        ExerciseSlot(
            name="Standing Calf Raise",
            sets=4,
            reps_min=15,
            reps_max=20,
            suggested_weight_kg=percentage_of_1rm(squat_1rm * 0.5, 60),
            rest_seconds=60,
            notes="Full range: deep stretch at bottom, peak contraction at top.",
        ),
    ]
