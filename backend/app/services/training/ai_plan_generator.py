"""AI-assisted workout plan generation for muscle-targeted sessions.

Picks exercises from the library via LLM for the requested muscles, and asks
for alternative swaps in the same call so the Alt UI needs no extra AI round-trip.
Weights still come from the progressive-overload / anchor prescription engine.
"""

from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logging import get_logger
from app.db.models.workout import Exercise
from app.services.llm.provider import get_llm
from app.services.training.personalized_generator import (
    UserTrainingContext,
    _exercise_modality,
    find_exercise_alternatives,
    prescribe_for_exercise,
)

logger = get_logger(__name__)

_BODYWEIGHT_NAME_HINTS = (
    "push-up", "push up", "pull-up", "pull up", "chin-up", "chin up",
    "dip", "plank", "burpee", "muscle-up", "inverted row", "hanging leg",
    "sit-up", "sit up", "crunch", "mountain climber", "jumping jack",
)

# Movements where external load is almost never logged (hide weight field)
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
        note = entry.get("notes") or ""
        bw_note = "Bodyweight movement — log reps only."
        entry["notes"] = f"{bw_note} {note}".strip() if note and bw_note not in note else (note or bw_note)
    elif meta["load_display"] == "per_hand":
        note = entry.get("notes") or ""
        db_note = "Enter the weight of EACH dumbbell (not combined)."
        if "EACH" not in note:
            entry["notes"] = f"{db_note} {note}".strip()
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


def _alt_payload(exercise: Exercise, ctx: UserTrainingContext) -> dict:
    slot = prescribe_for_exercise(exercise, ctx)
    meta = infer_load_meta(exercise)
    weight = 0.0 if meta["weight_irrelevant"] else slot.suggested_weight_kg
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
        "prescription": {
            "sets": slot.sets,
            "reps_min": slot.reps_min,
            "reps_max": slot.reps_max,
            "weight_kg": weight,
            "notes": slot.notes,
            "set_plan": [
                {
                    "set_number": n,
                    "weight_kg": weight,
                    "reps": slot.reps_min,
                }
                for n in range(1, slot.sets + 1)
            ],
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

    primary = [ex for ex in gym if ex.primary_muscle in muscles]
    secondary = [
        ex for ex in gym
        if ex not in primary
        and any(sm in muscles for sm in (ex.secondary_muscles or []))
    ]
    return primary + secondary[:40]


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


async def generate_ai_muscle_plan(
    *,
    session_name: str,
    muscle_groups: list[str],
    ctx: UserTrainingContext,
    all_exercises: list[Exercise],
    exclude_exercise_ids: set[str] | None = None,
    target_exercises: int = 5,
    alternatives_per_exercise: int = 3,
) -> list[dict] | None:
    """
    Ask the LLM to build a muscle-targeted gym session from the library.

    Returns plan entries (with baked-in alternatives) or None if AI fails —
    caller should fall back to the rule engine.
    """
    exclude = set(exclude_exercise_ids or [])
    pool = [
        ex for ex in _candidate_pool(all_exercises, muscle_groups)
        if str(ex.id) not in exclude
    ]
    if len(pool) < 3:
        logger.warning("AI plan: candidate pool too small", count=len(pool))
        return None

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

    familiar = [
        {"name": stats.exercise_name, "sets_logged": stats.set_count}
        for stats in list(ctx.exercise_stats.values())[:15]
    ]

    system = """You are an expert strength coach building a single gym workout.
You MUST only choose exercises from the provided catalog (by id).
Never invent exercises. Never pick swimming or cardio.
Match the requested target muscles — do not fill with unrelated muscles.
Return ONLY valid JSON."""

    user_prompt = f"""Build a workout plan.

Session name: {session_name}
Target muscles (primary focus): {", ".join(muscle_groups) or "full gym"}
Goal: {ctx.goal.value}
Bodyweight: {ctx.weight_kg:.0f} kg
Injuries / avoid: {", ".join(ctx.injuries) or "none"}
Disliked: {", ".join(ctx.disliked[:8]) or "none"}
Familiar lifts: {json.dumps(familiar) if familiar else "[]"}

Catalog (choose ONLY from these):
{json.dumps(catalog)}

Requirements:
1. Pick {target_exercises} main exercises that cover ALL of the target muscles
   (compounds first, then isolations). If multiple muscles were requested
   (e.g. back + biceps, or chest + shoulders + triceps), include work for
   each — do not ignore any requested muscle. Every main exercise's
   primary_muscle OR secondary_muscles MUST overlap the target muscles.
2. For EACH main exercise, also pick {alternatives_per_exercise} alternative
   exercise ids from the catalog that train a similar movement / same muscle
   (good swaps if equipment is busy or the user wants variety). Alternatives
   must not duplicate the main list.
3. Balance the session across the requested muscles only —
   do NOT include chest/legs/etc. unless those muscles were requested.

Return JSON exactly in this shape:
{{
  "rationale": "one short sentence",
  "exercises": [
    {{
      "exercise_id": "<catalog id>",
      "alternative_ids": ["<id>", "<id>", "<id>"]
    }}
  ]
}}"""

    try:
        llm = get_llm(temperature=0.35, max_tokens=1400)
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
        ex = by_id.get(eid)
        if not ex:
            name = str(row.get("name") or "").strip().lower()
            ex = by_name.get(name)
        if not ex or str(ex.id) in used:
            continue
        if muscle_groups:
            ok = (
                ex.primary_muscle in muscle_groups
                or any(sm in muscle_groups for sm in (ex.secondary_muscles or []))
            )
            if not ok:
                continue

        used.add(str(ex.id))
        slot = prescribe_for_exercise(ex, ctx)
        entry = _slot_to_entry(ex, slot)

        alt_ids = [str(a) for a in (row.get("alternative_ids") or []) if a]
        alt_exercises: list[Exercise] = []
        for aid in alt_ids:
            alt = by_id.get(aid)
            if not alt or str(alt.id) in used:
                continue
            if str(alt.id) in {str(a.id) for a in alt_exercises}:
                continue
            alt_exercises.append(alt)
            if len(alt_exercises) >= alternatives_per_exercise:
                break

        if len(alt_exercises) < alternatives_per_exercise:
            extra = find_exercise_alternatives(
                ex,
                all_exercises,
                ctx,
                exclude_ids=used | {str(a.id) for a in alt_exercises},
                limit=alternatives_per_exercise - len(alt_exercises),
            )
            alt_exercises.extend(extra)

        entry["alternatives"] = [
            _alt_payload(a, ctx) for a in alt_exercises[:alternatives_per_exercise]
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
