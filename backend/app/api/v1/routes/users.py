"""User profile and preferences API."""

from __future__ import annotations

import uuid
from datetime import date, time
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenPayload, get_current_user
from app.db.models.user import ActivityLevel, DietType, User, UserPreferences
from app.db.session import get_db

router = APIRouter(prefix="/users", tags=["Users"])


class UserProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    timezone: str
    is_onboarded: bool


class PreferencesUpdateRequest(BaseModel):
    height_cm: float | None = None
    current_weight_kg: float | None = None
    target_weight_kg: float | None = None
    date_of_birth: date | None = None
    diet_type: DietType | None = None
    allowed_foods: list[str] | None = None
    disallowed_foods: list[str] | None = None
    supplement_preferences: list[str] | None = None
    current_injuries: list[str] | None = None
    medical_conditions: list[str] | None = None
    work_start_time: str | None = None
    work_end_time: str | None = None
    gym_preferred_time: str | None = None
    swim_preferred_time: str | None = None
    current_sleep_time: str | None = None
    target_sleep_time: str | None = None
    activity_level: ActivityLevel | None = None
    motivation_triggers: list[str] | None = None
    rest_days: list[str] | None = None


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """Get the authenticated user's profile."""
    result = await db.execute(
        select(User).where(User.clerk_user_id == current_user.sub)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found. Please complete onboarding.",
        )

    return UserProfileResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        timezone=user.timezone,
        is_onboarded=user.is_onboarded,
    )


@router.post("/me/preferences", status_code=status.HTTP_200_OK)
async def update_preferences(
    request: PreferencesUpdateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update user preferences (permanent memory layer)."""
    result = await db.execute(
        select(User).where(User.clerk_user_id == current_user.sub)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    pref_result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    prefs = pref_result.scalar_one_or_none()

    if not prefs:
        prefs = UserPreferences(user_id=user.id)
        db.add(prefs)

    # Apply only the provided updates
    update_data = request.model_dump(exclude_none=True)
    for field, value in update_data.items():
        if hasattr(prefs, field):
            setattr(prefs, field, value)

    await db.flush()
    return {"status": "updated"}


@router.post("/onboard", status_code=status.HTTP_201_CREATED)
async def onboard_user(
    profile: PreferencesUpdateRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Complete user onboarding.

    Creates the user record (if not existing) and their initial preferences.
    Seeding the permanent memory layer with accurate initial data is critical
    for AI coaching quality from day one.
    """
    result = await db.execute(
        select(User).where(User.clerk_user_id == current_user.sub)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            clerk_user_id=current_user.sub,
            email=current_user.email or "",
            is_active=True,
        )
        db.add(user)
        await db.flush()

    # Create preferences
    prefs = UserPreferences(user_id=user.id)
    update_data = profile.model_dump(exclude_none=True)
    for field, value in update_data.items():
        if hasattr(prefs, field):
            setattr(prefs, field, value)

    db.add(prefs)
    user.is_onboarded = True
    await db.flush()

    return {"status": "onboarded", "user_id": str(user.id)}
