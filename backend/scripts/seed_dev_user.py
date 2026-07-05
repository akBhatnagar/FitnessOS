"""
Seed script for local development.

Creates a demo dev user with preferences, events, measurements, goals, and habits.
- User account + preferences
- Two key events (Pre-Wedding Shoot, Wedding)
- 5 weeks of weight measurements
- Primary fat-loss goal
- Four habits

Run with:
    .venv/bin/python scripts/seed_dev_user.py
"""

import asyncio
from datetime import date, datetime, timezone, timedelta, time as dtime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import os; DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://akshay@localhost:5432/fitnessos")
engine = create_async_engine(DATABASE_URL, echo=False)


async def seed() -> None:
    async with AsyncSession(engine) as session:
        async with session.begin():
            result = await session.execute(
                text("SELECT id FROM users WHERE clerk_user_id = 'dev-user-001'")
            )
            if result.scalar_one_or_none():
                print("Dev user already seeded. Skipping.")
                return

            user_id = str(uuid4())
            now = datetime.now(timezone.utc)

            # User
            await session.execute(text("""
                INSERT INTO users (id, clerk_user_id, email, full_name, timezone,
                                   is_active, is_onboarded, created_at, updated_at)
                VALUES (:id, 'dev-user-001', 'dev@fitnessos.local', 'Demo User',
                        'Asia/Kolkata', true, true, :now, :now)
            """), {"id": user_id, "now": now})

            # User Preferences
            await session.execute(text("""
                INSERT INTO user_preferences (
                    id, user_id,
                    height_cm, current_weight_kg, target_weight_kg,
                    diet_type, allowed_foods, disallowed_foods, food_allergies,
                    supplement_preferences, meal_timing_preferences,
                    work_start_time, work_end_time,
                    gym_preferred_time, swim_preferred_time,
                    current_sleep_time, target_sleep_time,
                    current_wake_time, target_wake_time,
                    rest_days, activity_level,
                    preferred_exercises, disliked_exercises,
                    current_injuries, medical_conditions,
                    motivation_triggers, coaching_style_preference, extra,
                    created_at, updated_at
                ) VALUES (
                    :id, :user_id,
                    185.4, 100.0, 85.0,
                    'vegetarian',
                    ARRAY['milk','paneer','curd','whey protein','eggs','protein bars']::varchar[],
                    ARRAY['tofu','soya chunks','creatine']::varchar[],
                    ARRAY[]::varchar[],
                    ARRAY[]::varchar[],
                    '{}',
                    :t_work_start, :t_work_end,
                    :t_gym, :t_swim,
                    :t_sleep, :t_sleep_goal,
                    :t_wake, :t_wake_goal,
                    ARRAY['saturday','sunday']::varchar[], 'moderately_active',
                    ARRAY['compound lifts','swimming']::varchar[],
                    ARRAY['burpees']::varchar[],
                    ARRAY[]::varchar[], ARRAY[]::varchar[],
                    ARRAY['visible progress','wedding countdown']::varchar[], 'motivational', '{}',
                    :now, :now
                )
            """), {"id": str(uuid4()), "user_id": user_id, "now": now,
                   "t_work_start": dtime(10, 30), "t_work_end": dtime(20, 0),
                   "t_gym": dtime(21, 0), "t_swim": dtime(8, 0),
                   "t_sleep": dtime(3, 0), "t_sleep_goal": dtime(0, 0),
                   "t_wake": dtime(10, 0), "t_wake_goal": dtime(7, 0)})

            # Events
            for title, event_date, event_type, peak_priority in [
                ("Pre-Wedding Shoot", date(2026, 10, 20), "photoshoot", "high"),
                ("Wedding", date(2027, 1, 30), "wedding", "critical"),
            ]:
                await session.execute(text("""
                    INSERT INTO events (
                        id, user_id, title, event_type, event_date,
                        is_active, peak_priority, planning_metadata,
                        created_at, updated_at
                    ) VALUES (
                        :id, :user_id, :title, :event_type, :event_date,
                        true, :peak_priority, '{}',
                        :now, :now
                    )
                """), {
                    "id": str(uuid4()), "user_id": user_id,
                    "title": title, "event_type": event_type,
                    "event_date": event_date, "peak_priority": peak_priority,
                    "now": now,
                })

            # Measurements — 5 weeks of declining weight (measured_on is a date)
            for i, weight in enumerate([102.0, 101.5, 101.0, 100.5, 100.0]):
                m_date = (now - timedelta(days=(4 - i) * 7)).date()
                await session.execute(text("""
                    INSERT INTO measurements (id, user_id, weight_kg, measured_on, created_at, updated_at)
                    VALUES (:id, :user_id, :weight, :m_date, :now, :now)
                """), {"id": str(uuid4()), "user_id": user_id,
                       "weight": weight, "m_date": m_date, "now": now})

            # Goal
            await session.execute(text("""
                INSERT INTO goals (
                    id, user_id, category, title, description,
                    current_value, target_value, unit,
                    target_date, priority, status, is_primary,
                    created_at, updated_at
                ) VALUES (
                    :id, :user_id, 'body_composition',
                    'Reach 85 kg for wedding',
                    'Lose 15 kg of fat while maintaining muscle. Primary goal is V-taper and visible definition.',
                    100.0, 85.0, 'kg',
                    '2027-01-15', 1, 'active', true,
                    :now, :now
                )
            """), {"id": str(uuid4()), "user_id": user_id, "now": now})

            # Habits
            for name, desc, target_time, category in [
                ("Evening Gym", "Strength training at gym", dtime(21, 0), "fitness"),
                ("Morning Swim", "Swimming practice at 8 AM", dtime(8, 0), "fitness"),
                ("Sleep by Midnight", "Go to sleep by 12 AM", dtime(0, 0), "sleep"),
                ("Daily Protein Target", "Hit 160g+ protein every day", dtime(20, 0), "nutrition"),
            ]:
                await session.execute(text("""
                    INSERT INTO habits (
                        id, user_id, name, description, frequency,
                        active_days, target_time, is_active, streak_current,
                        streak_best, category, ai_suggested, created_at, updated_at
                    ) VALUES (
                        :id, :user_id, :name, :desc, 'daily',
                        ARRAY['mon','tue','wed','thu','fri','sat','sun']::varchar[],
                        :target_time, true, 0, 0, :category, false, :now, :now
                    )
                """), {
                    "id": str(uuid4()), "user_id": user_id,
                    "name": name, "desc": desc,
                    "target_time": target_time, "category": category,
                    "now": now,
                })

        print("✅ Dev user seeded successfully!")
        print(f"   User ID  : {user_id}")
        print(f"   Clerk ID : dev-user-001")
        print(f"   Name     : Demo User")
        print(f"   Weight   : 100 kg → 85 kg goal")
        print(f"   Events   : Pre-Wedding (Oct 20 2026) + Wedding (Jan 30 2027)")
        print()
        print("   Open http://localhost:3000 to see the dashboard ✨")


if __name__ == "__main__":
    asyncio.run(seed())
