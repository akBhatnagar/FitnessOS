"""AI-assisted workout plan generation for muscle-targeted sessions.

Builds a rich, history-driven prompt (same-muscle sessions, body measurements,
per-exercise weight/reps) and asks the LLM for exercises, weekly prescriptions,
and same-muscle-part alternatives in one call.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models.user import User
from app.db.models.workout import Exercise
from app.services.llm.provider import get_llm
from app.services.training.personalized_generator import (
    UserTrainingContext,
    _exercise_modality,
    find_exercise_alternatives,
    prescribe_for_exercise,
)
from app.services.training.workout_plan_context import (
    build_ai_muscle_prompt,
    build_muscle_plan_prompt_context,
)

logger = get_logger(__name__)

_BODYWEIGHT_NAME_HINTS = (
    "push-up", "push up", "pull-up", "pull up", "chin-up", "chin up",
    "dip", "plank", "burpee", "muscle-up", "inverted row", "hanging leg",
    "sit-up", "sit up", "crunch", "mountain climber", "jumping jack",
)

_WEIGHT_IRRELEVANT_HINTS = (
    "push-up", "push up", "plank", "burpee", "sit-up", "sit up",
    "crunch", "mountain climber", "jumping jack",
)


def infer_load_meta(exercise: Exercise) -> dict[str, Any]:
    """How load should be displayed / entered for this exercise."""
    equipment = [str(e).lower() for e in (exercise.equipment_needed or [])]
    tags = {str(t).lower() for t in (exercise.tags or [])}
    etype = str(exercise.exercise_type or "").lower()
    name = exercise.name.lower()

    is_bodyweight = (
        etype == "bodyweight"
        or "bodyweight" in equipment
        or "bodyweight" in tags
        or "no_equipment" in tags
        or any(h in name for h in _BODYWEIGHT_NAME_HINTS)
    )
    weight_irrelevant = (
        any(h in name for h in _WEIGHT_IRRELEVANT_HINTS)
        or (
            is_bodyweight
            and not any(
                x in equipment
                for x in ("barbell", "dumbbells", "cable", "machine", "smith_machine", "pull_up_bar")
            )
            and not any(h in name for h in ("pull-up", "pull up", "chin-up", "chin up", "dip"))
        )
    )

    if weight_irrelevant:
        load_display = "bodyweight"
        load_label = "Bodyweight — no load to enter"
    elif "dumbbells" in equipment or "dumbbell" in name:
        load_display = "per_hand"
        load_label = "kg each dumbbell"
    elif "kettlebell" in " ".join(equipment) or "kettlebell" in name:
        load_display = "per_hand"
        load_label = "kg each kettlebell"
    else:
        load_display = "total"
        load_label = "kg total"

    return {
        "weight_irrelevant": weight_irrelevant,
        "load_display": load_display,
        "load_label": load_label,
        "equipment": list(exercise.equipment_needed or []),
    }


def _apply_load_meta(entry: dict, exercise: Exercise) -> dict:
    meta = infer_load_meta(exercise)
    entry.update(meta)
    if meta["weight_irrelevant"]:
        for s in entry.get("sets", []):
            s["weight_kg"] = 0.0
    return entry


def _slot_to_entry(exercise: Exercise, slot) -> dict:
    meta = infer_load_meta(exercise)
    weight = 0.0 if meta["weight_irrelevant"] else slot.suggested_weight_kg
    entry = {
        "exercise_id": str(exercise.id),
        "name": exercise.name,
        "primary_muscle": exercise.primary_muscle,
        "is_compound": exercise.is_compound,
        "tips": exercise.tips,
        "notes": slot.notes,
        "sets": [
            {
                "set_number": n,
                "weight_kg": weight,
                "reps": slot.reps_min,
            }
            for n in range(1, slot.sets + 1)
        ],
    }
    return _apply_load_meta(entry, exercise)


def _normalize_ai_sets(
    raw_sets: Any,
    *,
    exercise: Exercise,
    ctx: UserTrainingContext,
    fallback_slot=None,
) -> list[dict]:
    """Validate AI sets; fall back to rule-engine prescription when missing/invalid."""
    slot = fallback_slot or prescribe_for_exercise(exercise, ctx)
    meta = infer_load_meta(exercise)

    if not isinstance(raw_sets, list) or not raw_sets:
        weight = 0.0 if meta["weight_irrelevant"] else slot.suggested_weight_kg
        return [
            {"set_number": n, "weight_kg": weight, "reps": slot.reps_min}
            for n in range(1, slot.sets + 1)
        ]

    normalized: list[dict] = []
    for idx, row in enumerate(raw_sets[:5], start=1):
        if not isinstance(row, dict):
            continue
        try:
            reps = int(row.get("reps") or slot.reps_min)
            reps = max(1, min(reps, 30))
        except (TypeError, ValueError):
            reps = slot.reps_min
        try:
            weight = float(row.get("weight_kg") if row.get("weight_kg") is not None else 0)
            weight = max(0.0, weight)
        except (TypeError, ValueError):
            weight = 0.0
        if meta["weight_irrelevant"]:
            weight = 0.0
        set_num = int(row.get("set_number") or idx)
        normalized.append({"set_number": set_num, "weight_kg": weight, "reps": reps})

    if len(normalized) < 2:
        weight = 0.0 if meta["weight_irrelevant"] else slot.suggested_weight_kg
        return [
            {"set_number": n, "weight_kg": weight, "reps": slot.reps_min}
            for n in range(1, slot.sets + 1)
        ]

    for i, s in enumerate(normalized, start=1):
        s["set_number"] = i
    return normalized


def _alt_payload(
    exercise: Exercise,
    ctx: UserTrainingContext,
    *,
    ai_sets: Any = None,
    swap_reason: str | None = None,
) -> dict:
    slot = prescribe_for_exercise(exercise, ctx)
    sets = _normalize_ai_sets(ai_sets, exercise=exercise, ctx=ctx, fallback_slot=slot)
    meta = infer_load_meta(exercise)
    avg_weight = sets[0]["weight_kg"] if sets else 0.0
    avg_reps = sets[0]["reps"] if sets else slot.reps_min
    return {
        "id": str(exercise.id),
        "name": exercise.name,
        "primary_muscle": exercise.primary_muscle,
        "is_compound": exercise.is_compound,
        "tips": exercise.tips,
        "equipment": list(exercise.equipment_needed or []),
        "tags": list(exercise.tags or []),
        "weight_irrelevant": meta["weight_irrelevant"],
        "load_display": meta["load_display"],
        "load_label": meta["load_label"],
        "swap_reason": swap_reason,
        "prescription": {
            "sets": len(sets),
            "reps_min": avg_reps,
            "reps_max": avg_reps,
            "weight_kg": avg_weight,
            "notes": swap_reason or "",
            "set_plan": sets,
        },
    }


def _candidate_pool(
    all_exercises: list[Exercise],
    muscle_groups: list[str],
) -> list[Exercise]:
    muscles = set(muscle_groups or [])
    gym = [ex for ex in all_exercises if _exercise_modality(ex) == "strength"]
    if not muscles:
        return gym
    return [ex for ex in gym if ex.primary_muscle in muscles]


def _parse_json(content: str) -> dict:
    cleaned = (content or "").strip()
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        cleaned = parts[1] if len(parts) > 1 else cleaned
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned.strip())


def _resolve_exercise(
    eid: str,
    by_id: dict[str, Exercise],
    by_name: dict[str, Exercise],
    name_hint: str = "",
) -> Exercise | None:
    ex = by_id.get(str(eid).strip())
    if ex:
        return ex
    if name_hint:
        return by_name.get(name_hint.strip().lower())
    return None


async def generate_ai_muscle_plan(
    *,
    db: AsyncSession,
    user: User,
    session_name: str,
    muscle_groups: list[str],
    ctx: UserTrainingContext,
    all_exercises: list[Exercise],
    exclude_exercise_ids: set[str] | None = None,
    target_exercises: int = 5,
    alternatives_per_exercise: int = 3,
) -> list[dict] | None:
    """
    Ask the LLM to build a muscle-targeted gym session from history + catalog.

    Returns plan entries (with AI-prescribed sets and baked-in alternatives)
    or None if AI fails — caller should fall back to the rule engine.
    """
    exclude = set(exclude_exercise_ids or [])
    pool = [
        ex for ex in _candidate_pool(all_exercises, muscle_groups)
        if str(ex.id) not in exclude
    ]
    if len(pool) < 3:
        logger.warning("AI plan: candidate pool too small", count=len(pool))
        return None

    exercise_by_id = {str(ex.id): ex for ex in all_exercises}

    familiar_ids = set(ctx.exercise_stats.keys())
    preferred_names = {p.lower() for p in ctx.preferred}
    ranked = sorted(
        pool,
        key=lambda ex: (
            0 if str(ex.id) in familiar_ids else 1,
            0 if ex.name.lower() in preferred_names else 1,
            0 if ex.is_compound else 1,
            ex.name,
        ),
    )[:60]

    by_id = {str(ex.id): ex for ex in ranked}
    by_name = {ex.name.lower(): ex for ex in ranked}

    catalog = [
        {
            "id": str(ex.id),
            "name": ex.name,
            "primary_muscle": ex.primary_muscle,
            "secondary_muscles": list(ex.secondary_muscles or [])[:4],
            "is_compound": ex.is_compound,
            "equipment": list(ex.equipment_needed or [])[:4],
        }
        for ex in ranked
    ]

    prompt_ctx = await build_muscle_plan_prompt_context(
        db, user, ctx, muscle_groups, exercise_by_id
    )
    system, user_prompt = build_ai_muscle_prompt(
        session_name=session_name,
        muscle_groups=muscle_groups,
        ctx=ctx,
        prompt_ctx=prompt_ctx,
        catalog=catalog,
        target_exercises=target_exercises,
        alternatives_per_exercise=alternatives_per_exercise,
    )

    try:
        llm = get_llm(temperature=0.3, max_tokens=3200)
        response = await llm.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=user_prompt),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_json(raw if isinstance(raw, str) else str(raw))
    except Exception as exc:
        logger.warning("AI plan generation failed", error=str(exc))
        return None

    picked_rows = parsed.get("exercises") or []
    if not isinstance(picked_rows, list) or not picked_rows:
        logger.warning("AI plan returned no exercises")
        return None

    used: set[str] = set()
    entries: list[dict] = []

    for row in picked_rows:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("exercise_id") or "").strip()
        ex = _resolve_exercise(eid, by_id, by_name, str(row.get("name") or ""))
        if not ex or str(ex.id) in used:
            continue
        if muscle_groups and ex.primary_muscle not in muscle_groups:
            continue

        used.add(str(ex.id))
        slot = prescribe_for_exercise(ex, ctx)
        sets = _normalize_ai_sets(row.get("sets"), exercise=ex, ctx=ctx, fallback_slot=slot)
        entry = {
            "exercise_id": str(ex.id),
            "name": ex.name,
            "primary_muscle": ex.primary_muscle,
            "is_compound": ex.is_compound,
            "tips": ex.tips,
            "notes": str(row.get("notes") or slot.notes or ""),
            "sets": sets,
        }
        entry = _apply_load_meta(entry, ex)

        alt_rows = row.get("alternatives") or []
        if not isinstance(alt_rows, list):
            alt_rows = []
        alt_exercises: list[tuple[Exercise, dict]] = []

        for alt_row in alt_rows:
            if not isinstance(alt_row, dict):
                continue
            aid = str(alt_row.get("exercise_id") or "").strip()
            alt = _resolve_exercise(aid, by_id, by_name)
            if not alt or str(alt.id) in used:
                continue
            if str(alt.id) in {str(a[0].id) for a in alt_exercises}:
                continue
            if muscle_groups and alt.primary_muscle not in muscle_groups:
                continue
            alt_exercises.append((alt, alt_row))
            if len(alt_exercises) >= alternatives_per_exercise:
                break

        if len(alt_exercises) < alternatives_per_exercise:
            extra = find_exercise_alternatives(
                ex,
                all_exercises,
                ctx,
                exclude_ids=used | {str(a[0].id) for a in alt_exercises},
                limit=alternatives_per_exercise - len(alt_exercises) + 4,
            )
            for alt in extra:
                if muscle_groups and alt.primary_muscle not in muscle_groups:
                    continue
                if str(alt.id) in used or str(alt.id) in {str(a[0].id) for a in alt_exercises}:
                    continue
                alt_exercises.append((alt, {}))
                if len(alt_exercises) >= alternatives_per_exercise:
                    break

        entry["alternatives"] = [
            _alt_payload(
                alt,
                ctx,
                ai_sets=alt_row.get("sets"),
                swap_reason=str(alt_row.get("swap_reason") or "") or None,
            )
            for alt, alt_row in alt_exercises[:alternatives_per_exercise]
        ]
        entries.append(entry)

        if len(entries) >= target_exercises:
            break

    if len(entries) < 3:
        logger.warning("AI plan produced too few valid exercises", count=len(entries))
        return None

    rationale = parsed.get("rationale")
    if rationale:
        ctx.personalization_notes.insert(0, str(rationale))

    logger.info(
        "AI muscle plan generated",
        session=session_name,
        exercises=len(entries),
        muscles=muscle_groups,
        prior_sessions=len(prompt_ctx.same_muscle_sessions),
        history_exercises=len(prompt_ctx.muscle_exercise_history),
    )
    return entries


def enrich_entries_with_alternatives(
    entries: list[dict],
    *,
    exercise_by_id: dict[str, Exercise],
    all_exercises: list[Exercise],
    ctx: UserTrainingContext,
    alternatives_per_exercise: int = 3,
) -> list[dict]:
    """Attach load metadata + alternatives to rule-engine plan entries."""
    used = {e["exercise_id"] for e in entries}
    enriched: list[dict] = []
    for entry in entries:
        ex = exercise_by_id.get(entry["exercise_id"])
        if not ex:
            enriched.append(entry)
            continue
        entry = _apply_load_meta(dict(entry), ex)
        if "alternatives" not in entry:
            alts = find_exercise_alternatives(
                ex,
                all_exercises,
                ctx,
                exclude_ids=used,
                limit=alternatives_per_exercise,
            )
            entry["alternatives"] = [_alt_payload(a, ctx) for a in alts]
        enriched.append(entry)
    return enriched
