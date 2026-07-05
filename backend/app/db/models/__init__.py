"""
SQLAlchemy model exports.

Import all models here so Alembic's autogenerate can discover them.
"""

from app.db.models.user import User, UserPreferences
from app.db.models.goal import Goal
from app.db.models.event import Event
from app.db.models.measurement import Measurement, ProgressPhoto
from app.db.models.workout import (
    Exercise,
    WorkoutPlan,
    WorkoutSession,
    WorkoutSet,
    ExerciseHistory,
)
from app.db.models.nutrition import (
    Food,
    Recipe,
    NutritionPlan,
    Meal,
    MealItem,
    Supplement,
)
from app.db.models.swimming import SwimmingPlan, SwimmingSession
from app.db.models.habit import Habit, HabitLog
from app.db.models.memory import ConversationMessage, MemoryStore, Embedding
from app.db.models.analytics import WeeklyReview, MonthlyReport, Prediction, Achievement
from app.db.models.notification import Notification
from app.db.models.coach import CoachNote
from app.db.models.audit import AuditLog

__all__ = [
    "User",
    "UserPreferences",
    "Goal",
    "Event",
    "Measurement",
    "ProgressPhoto",
    "Exercise",
    "WorkoutPlan",
    "WorkoutSession",
    "WorkoutSet",
    "ExerciseHistory",
    "Food",
    "Recipe",
    "NutritionPlan",
    "Meal",
    "MealItem",
    "Supplement",
    "SwimmingPlan",
    "SwimmingSession",
    "Habit",
    "HabitLog",
    "ConversationMessage",
    "MemoryStore",
    "Embedding",
    "WeeklyReview",
    "MonthlyReport",
    "Prediction",
    "Achievement",
    "Notification",
    "CoachNote",
    "AuditLog",
]
