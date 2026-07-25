"""
Nutrition Tracker API — meal logging, food search, macro tracking.

Endpoints:
- GET  /nutrition/foods              — search food database
- GET  /nutrition/today              — today's macros summary + meals
- GET  /nutrition/history            — meal history by date range
- POST /nutrition/meals              — log a new meal
- POST /nutrition/meals/:id/items    — add food item to meal
- DELETE /nutrition/meals/:id        — delete a meal
- GET  /nutrition/targets            — user's daily macro targets
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenPayload, get_current_user
from app.db.models.user import User, UserPreferences
from app.db.models.nutrition import Food as FoodItem, Meal, MealItem
from app.db.session import get_db
from app.core.logging import get_logger

router = APIRouter(prefix="/nutrition", tags=["Nutrition"])
logger = get_logger("api.nutrition")


# ─── Models ──────────────────────────────────────────────────────────────────

class LogMealRequest(BaseModel):
    meal_type: str = Field(description="breakfast, lunch, dinner, snack, pre_workout, post_workout")
    name: Optional[str] = Field(None, max_length=255)
    meal_date: date = Field(default_factory=date.today)
    meal_time: Optional[str] = Field(None, description="HH:MM format")
    notes: Optional[str] = None
    restaurant_name: Optional[str] = None


class AddFoodItemRequest(BaseModel):
    food_id: Optional[str] = Field(None, description="ID from food_database table")
    food_name: str = Field(min_length=1, max_length=255)
    quantity_g: float = Field(gt=0, le=2000, description="Weight in grams")
    # Manual entry (used when food_id not provided)
    calories_override: Optional[float] = None
    protein_override: Optional[float] = None
    carbs_override: Optional[float] = None
    fat_override: Optional[float] = None


class QuickLogRequest(BaseModel):
    """Log a complete meal with items in one shot."""
    meal_type: str
    meal_date: date = Field(default_factory=date.today)
    name: Optional[str] = None
    items: list[AddFoodItemRequest] = []


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _get_user(clerk_id: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _macros_from_food(food: FoodItem, quantity_g: float) -> dict:
    factor = quantity_g / 100.0
    return {
        "calories": round(float(food.calories_per_100g) * factor, 1),
        "protein_g": round(float(food.protein_g) * factor, 1),
        "carbs_g": round(float(food.carbs_g) * factor, 1),
        "fat_g": round(float(food.fat_g) * factor, 1),
    }


def _macros_to_per_100g(
    quantity_g: float,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
) -> dict[str, Decimal]:
    factor = Decimal("100") / Decimal(str(quantity_g))
    return {
        "calories_per_100g": Decimal(str(round(calories * float(factor), 2))),
        "protein_g": Decimal(str(round(protein_g * float(factor), 2))),
        "carbs_g": Decimal(str(round(carbs_g * float(factor), 2))),
        "fat_g": Decimal(str(round(fat_g * float(factor), 2))),
    }


def _food_to_search_dict(food: FoodItem, user_id: uuid.UUID) -> dict:
    is_custom = bool(food.is_user_created and food.created_by_user_id == user_id)
    return {
        "id": str(food.id),
        "name": food.name,
        "is_vegetarian": food.is_vegetarian,
        "is_vegan": food.is_vegan,
        "is_custom": is_custom,
        "calories_per_100g": float(food.calories_per_100g),
        "protein_g": float(food.protein_g),
        "carbs_g": float(food.carbs_g),
        "fat_g": float(food.fat_g),
        "fiber_g": float(food.fiber_g) if food.fiber_g else None,
        "serving_size_g": float(food.serving_size_g) if food.serving_size_g else None,
        "serving_description": food.serving_description,
        "tags": food.tags,
        "per_serving": {
            "calories": round(float(food.calories_per_100g) * float(food.serving_size_g or 100) / 100, 1),
            "protein_g": round(float(food.protein_g) * float(food.serving_size_g or 100) / 100, 1),
        } if food.serving_size_g else None,
    }


async def _upsert_user_food(
    user: User,
    name: str,
    quantity_g: float,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    db: AsyncSession,
) -> FoodItem:
    """Save or update a user-created food in the library (macros normalised per 100g)."""
    clean_name = name.strip()
    per_100g = _macros_to_per_100g(quantity_g, calories, protein_g, carbs_g, fat_g)

    existing_result = await db.execute(
        select(FoodItem).where(
            FoodItem.is_user_created.is_(True),
            FoodItem.created_by_user_id == user.id,
            func.lower(FoodItem.name) == clean_name.lower(),
        )
    )
    food = existing_result.scalar_one_or_none()

    if food:
        food.calories_per_100g = per_100g["calories_per_100g"]
        food.protein_g = per_100g["protein_g"]
        food.carbs_g = per_100g["carbs_g"]
        food.fat_g = per_100g["fat_g"]
        food.serving_size_g = Decimal(str(quantity_g))
        food.serving_description = f"{quantity_g}g serving"
        if "custom" not in (food.tags or []):
            food.tags = list(food.tags or []) + ["custom"]
    else:
        food = FoodItem(
            name=clean_name,
            is_vegetarian=True,
            is_vegan=False,
            is_user_created=True,
            created_by_user_id=user.id,
            calories_per_100g=per_100g["calories_per_100g"],
            protein_g=per_100g["protein_g"],
            carbs_g=per_100g["carbs_g"],
            fat_g=per_100g["fat_g"],
            serving_size_g=Decimal(str(quantity_g)),
            serving_description=f"{quantity_g}g serving",
            tags=["custom"],
        )
        db.add(food)

    await db.flush()
    return food


async def _backfill_orphaned_meal_items(user: User, db: AsyncSession) -> int:
    """Create food_database entries for past manual meal items missing food_id."""
    result = await db.execute(
        select(MealItem)
        .join(Meal, MealItem.meal_id == Meal.id)
        .where(Meal.user_id == user.id, MealItem.food_id.is_(None))
    )
    items = result.scalars().all()
    if not items:
        return 0

    name_to_food_id: dict[str, uuid.UUID] = {}
    updated = 0

    for item in items:
        name_key = item.food_name.strip().lower()
        qty = float(item.quantity_g)
        if qty <= 0:
            continue

        if name_key not in name_to_food_id:
            food = await _upsert_user_food(
                user,
                item.food_name,
                qty,
                float(item.calories or 0),
                float(item.protein_g or 0),
                float(item.carbs_g or 0),
                float(item.fat_g or 0),
                db,
            )
            name_to_food_id[name_key] = food.id

        item.food_id = name_to_food_id[name_key]
        updated += 1

    if updated:
        await db.commit()
    return updated


def _meal_to_dict(meal: Meal, items: list = []) -> dict:
    return {
        "id": str(meal.id),
        "meal_type": meal.meal_type,
        "name": meal.name,
        "meal_date": meal.meal_date.isoformat(),
        "meal_time": str(meal.meal_time) if meal.meal_time else None,
        "total_calories": float(meal.total_calories) if meal.total_calories else 0,
        "total_protein_g": float(meal.total_protein_g) if meal.total_protein_g else 0,
        "total_carbs_g": float(meal.total_carbs_g) if meal.total_carbs_g else 0,
        "total_fat_g": float(meal.total_fat_g) if meal.total_fat_g else 0,
        "notes": meal.notes,
        "restaurant_name": meal.restaurant_name,
        "items": [
            {
                "id": str(i.id),
                "food_name": i.food_name,
                "quantity_g": float(i.quantity_g),
                "calories": float(i.calories) if i.calories else 0,
                "protein_g": float(i.protein_g) if i.protein_g else 0,
                "carbs_g": float(i.carbs_g) if i.carbs_g else 0,
                "fat_g": float(i.fat_g) if i.fat_g else 0,
            }
            for i in items
        ],
    }


async def _recalculate_meal_totals(meal: Meal, db: AsyncSession) -> None:
    """Recompute meal totals from its items."""
    result = await db.execute(
        select(
            func.coalesce(func.sum(MealItem.calories), 0).label("calories"),
            func.coalesce(func.sum(MealItem.protein_g), 0).label("protein_g"),
            func.coalesce(func.sum(MealItem.carbs_g), 0).label("carbs_g"),
            func.coalesce(func.sum(MealItem.fat_g), 0).label("fat_g"),
        ).where(MealItem.meal_id == meal.id)
    )
    row = result.one()
    meal.total_calories = row.calories
    meal.total_protein_g = row.protein_g
    meal.total_carbs_g = row.carbs_g
    meal.total_fat_g = row.fat_g


# ─── Food Search ─────────────────────────────────────────────────────────────

@router.get("/foods")
async def search_foods(
    query: str = "",
    vegetarian_only: bool = True,
    custom_only: bool = False,
    tag: str | None = None,
    limit: int = Query(20, le=50),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    Search the food database including the user's saved custom foods.
    """
    user = await _get_user(current_user.sub, db)
    await _backfill_orphaned_meal_items(user, db)

    stmt = select(FoodItem)

    if custom_only:
        stmt = stmt.where(
            FoodItem.is_user_created.is_(True),
            FoodItem.created_by_user_id == user.id,
        )
    elif vegetarian_only:
        stmt = stmt.where(
            or_(
                and_(
                    FoodItem.is_user_created.is_(True),
                    FoodItem.created_by_user_id == user.id,
                ),
                FoodItem.is_vegetarian.is_(True),
            )
        )

    if query:
        stmt = stmt.where(FoodItem.name.ilike(f"%{query}%"))
    if tag:
        stmt = stmt.where(FoodItem.tags.any(tag))

    stmt = stmt.order_by(
        FoodItem.is_user_created.desc(),
        FoodItem.name,
    ).limit(limit)

    result = await db.execute(stmt)
    foods = result.scalars().all()

    return [_food_to_search_dict(f, user.id) for f in foods]


# ─── Today's Summary ──────────────────────────────────────────────────────────

@router.get("/today")
async def get_today_summary(
    date_param: Optional[date] = Query(None, alias="date", description="YYYY-MM-DD, defaults to today"),
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Daily nutrition summary: totals, macro breakdown, meals, remaining targets.
    Pass ?date=YYYY-MM-DD to view or log for a previous day.
    """
    user = await _get_user(current_user.sub, db)
    target_date = date_param or date.today()
    if target_date > date.today():
        raise HTTPException(status_code=400, detail="Cannot view future dates")

    # Get user's targets
    prefs_result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    prefs = prefs_result.scalar_one_or_none()

    target_calories = 2200  # default deficit for ~100kg male
    target_protein = 160    # 1.6g/kg at 100kg
    target_carbs = 220
    target_fat = 70

    if prefs and prefs.current_weight_kg:
        w = float(prefs.current_weight_kg)
        target_protein = round(w * 1.6)
        target_calories = round(w * 22)  # approximate for moderate deficit

    # Get all meals for the selected day
    meals_result = await db.execute(
        select(Meal)
        .where(Meal.user_id == user.id, Meal.meal_date == target_date)
        .order_by(Meal.meal_time)
    )
    meals = meals_result.scalars().all()

    # Get items for each meal
    meal_dicts = []
    total_calories = 0.0
    total_protein = 0.0
    total_carbs = 0.0
    total_fat = 0.0

    for meal in meals:
        items_result = await db.execute(
            select(MealItem).where(MealItem.meal_id == meal.id)
        )
        items = items_result.scalars().all()
        meal_dicts.append(_meal_to_dict(meal, items))
        total_calories += float(meal.total_calories or 0)
        total_protein += float(meal.total_protein_g or 0)
        total_carbs += float(meal.total_carbs_g or 0)
        total_fat += float(meal.total_fat_g or 0)

    # Protein score (most important metric)
    protein_pct = min(100, round(total_protein / target_protein * 100))
    calorie_pct = min(100, round(total_calories / target_calories * 100))

    return {
        "date": target_date.isoformat(),
        "totals": {
            "calories": round(total_calories, 1),
            "protein_g": round(total_protein, 1),
            "carbs_g": round(total_carbs, 1),
            "fat_g": round(total_fat, 1),
        },
        "targets": {
            "calories": target_calories,
            "protein_g": target_protein,
            "carbs_g": target_carbs,
            "fat_g": target_fat,
        },
        "remaining": {
            "calories": max(0, round(target_calories - total_calories)),
            "protein_g": max(0, round(target_protein - total_protein, 1)),
            "carbs_g": max(0, round(target_carbs - total_carbs, 1)),
            "fat_g": max(0, round(target_fat - total_fat, 1)),
        },
        "scores": {
            "protein_pct": protein_pct,
            "calorie_pct": calorie_pct,
        },
        "meals": meal_dicts,
        "insight": _generate_daily_insight(total_protein, target_protein, total_calories, target_calories),
    }


def _generate_daily_insight(protein: float, protein_target: float, calories: float, cal_target: float) -> str:
    remaining_protein = protein_target - protein
    if remaining_protein <= 0:
        return f"Protein target hit! 🎯 You're in a {round(cal_target - calories)} kcal deficit."
    elif remaining_protein <= 40:
        return f"Almost there — {round(remaining_protein)}g protein to go. One whey shake + 100g paneer will do it."
    else:
        return f"{round(remaining_protein)}g protein remaining. Prioritise paneer, dal, and whey to hit your target."


# ─── Log Meal ─────────────────────────────────────────────────────────────────

@router.post("/meals", status_code=status.HTTP_201_CREATED)
async def log_meal(
    request: LogMealRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create an empty meal container. Add food items with /meals/:id/items."""
    user = await _get_user(current_user.sub, db)

    if request.meal_date > date.today():
        raise HTTPException(status_code=400, detail="Cannot log meals for future dates")

    meal_time = None
    if request.meal_time:
        h, m = request.meal_time.split(":")
        meal_time = time(int(h), int(m))

    meal = Meal(
        user_id=user.id,
        meal_type=request.meal_type,
        name=request.name or request.meal_type.replace("_", " ").title(),
        meal_date=request.meal_date,
        meal_time=meal_time,
        notes=request.notes,
        restaurant_name=request.restaurant_name,
        total_calories=0,
        total_protein_g=0,
        total_carbs_g=0,
        total_fat_g=0,
    )
    db.add(meal)
    await db.flush()
    await db.commit()

    return {"id": str(meal.id), "meal_type": meal.meal_type, "name": meal.name}


@router.post("/meals/{meal_id}/items", status_code=status.HTTP_201_CREATED)
async def add_food_item(
    meal_id: str,
    request: AddFoodItemRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Add a food item to a meal.

    If food_id is provided, macros are calculated from the food database.
    Otherwise, manual override values are used.
    """
    user = await _get_user(current_user.sub, db)

    # Verify meal belongs to user
    meal_result = await db.execute(
        select(Meal).where(Meal.id == uuid.UUID(meal_id), Meal.user_id == user.id)
    )
    meal = meal_result.scalar_one_or_none()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    calories = request.calories_override
    protein_g = request.protein_override
    carbs_g = request.carbs_override
    fat_g = request.fat_override
    food_db_id = None

    # Look up macros from food database
    if request.food_id:
        food_result = await db.execute(
            select(FoodItem).where(FoodItem.id == uuid.UUID(request.food_id))
        )
        food = food_result.scalar_one_or_none()
        if food:
            macros = _macros_from_food(food, request.quantity_g)
            calories = macros["calories"]
            protein_g = macros["protein_g"]
            carbs_g = macros["carbs_g"]
            fat_g = macros["fat_g"]
            food_db_id = food.id
    elif calories is not None and protein_g is not None:
        # Manual entry — persist to user's food library for future use
        saved_food = await _upsert_user_food(
            user,
            request.food_name,
            request.quantity_g,
            calories,
            protein_g,
            carbs_g or 0,
            fat_g or 0,
            db,
        )
        food_db_id = saved_food.id

    item = MealItem(
        meal_id=meal.id,
        food_id=food_db_id,
        food_name=request.food_name,
        quantity_g=request.quantity_g,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
    )
    db.add(item)
    await db.flush()

    # Recompute meal totals
    await _recalculate_meal_totals(meal, db)
    await db.commit()

    logger.info(
        "Food item logged",
        user=current_user.sub,
        food=request.food_name,
        protein=protein_g,
        calories=calories,
    )

    return {
        "item_id": str(item.id),
        "food_id": str(food_db_id) if food_db_id else None,
        "food_name": request.food_name,
        "quantity_g": request.quantity_g,
        "calories": calories,
        "protein_g": protein_g,
        "meal_totals": {
            "calories": float(meal.total_calories or 0),
            "protein_g": float(meal.total_protein_g or 0),
        },
    }


@router.post("/meals/quick-log", status_code=status.HTTP_201_CREATED)
async def quick_log_meal(
    request: QuickLogRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Log a complete meal with all items in one API call.
    Useful for logging a known meal (e.g., 'lunch — dal + rice + paneer').
    """
    user = await _get_user(current_user.sub, db)

    meal = Meal(
        user_id=user.id,
        meal_type=request.meal_type,
        name=request.name or request.meal_type.replace("_", " ").title(),
        meal_date=request.meal_date,
        total_calories=0,
        total_protein_g=0,
        total_carbs_g=0,
        total_fat_g=0,
    )
    db.add(meal)
    await db.flush()

    for item_req in request.items:
        calories = item_req.calories_override
        protein_g = item_req.protein_override
        carbs_g = item_req.carbs_override
        fat_g = item_req.fat_override
        food_db_id = None

        if item_req.food_id:
            food_result = await db.execute(
                select(FoodItem).where(FoodItem.id == uuid.UUID(item_req.food_id))
            )
            food = food_result.scalar_one_or_none()
            if food:
                macros = _macros_from_food(food, item_req.quantity_g)
                calories = macros["calories"]
                protein_g = macros["protein_g"]
                carbs_g = macros["carbs_g"]
                fat_g = macros["fat_g"]
                food_db_id = food.id
        elif item_req.calories_override is not None and item_req.protein_override is not None:
            saved_food = await _upsert_user_food(
                user,
                item_req.food_name,
                item_req.quantity_g,
                item_req.calories_override,
                item_req.protein_override,
                item_req.carbs_override or 0,
                item_req.fat_override or 0,
                db,
            )
            food_db_id = saved_food.id

        item = MealItem(
            meal_id=meal.id,
            food_id=food_db_id,
            food_name=item_req.food_name,
            quantity_g=item_req.quantity_g,
            calories=calories,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
        )
        db.add(item)

    await db.flush()
    await _recalculate_meal_totals(meal, db)
    await db.commit()

    return {
        "meal_id": str(meal.id),
        "meal_type": meal.meal_type,
        "total_calories": float(meal.total_calories or 0),
        "total_protein_g": float(meal.total_protein_g or 0),
        "items_logged": len(request.items),
    }


@router.delete("/meals/{meal_id}")
async def delete_meal(
    meal_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a meal and all its items."""
    user = await _get_user(current_user.sub, db)

    result = await db.execute(
        select(Meal).where(Meal.id == uuid.UUID(meal_id), Meal.user_id == user.id)
    )
    meal = result.scalar_one_or_none()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    await db.delete(meal)
    await db.commit()
    return {"deleted": meal_id}


@router.get("/targets")
async def get_macro_targets(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """User's personalised daily macro targets based on current weight and goals."""
    user = await _get_user(current_user.sub, db)

    prefs_result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    prefs = prefs_result.scalar_one_or_none()

    weight = float(prefs.current_weight_kg) if prefs and prefs.current_weight_kg else 100.0
    target_weight = float(prefs.target_weight_kg) if prefs and prefs.target_weight_kg else 85.0

    protein = round(weight * 1.7)  # slightly above minimum for muscle protection
    calories = round(weight * 22)   # mild deficit
    fat = round(weight * 0.8)
    carbs = round((calories - protein * 4 - fat * 9) / 4)

    return {
        "calories": calories,
        "protein_g": protein,
        "carbs_g": max(100, carbs),
        "fat_g": fat,
        "fiber_g": 30,
        "water_ml": 3500,
        "notes": [
            f"Based on current weight {weight}kg → target {target_weight}kg",
            f"Protein at 1.7g/kg to preserve muscle during fat loss",
            f"Deficit of ~{round(weight * 30) - calories} kcal/day from maintenance",
        ],
    }
