"""
Celery application configuration for background tasks.

Background workers handle:
- Weekly review generation (every Sunday)
- Embedding generation for new memories
- Plan adjustment after missed sessions
- Notification scheduling
- Monthly report generation
"""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "fitnessos",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.reviews",
        "app.workers.tasks.embeddings",
        "app.workers.tasks.notifications",
        "app.workers.tasks.analytics",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# ---- Periodic Tasks (Beat Schedule) ----
celery_app.conf.beat_schedule = {
    # Weekly review — every Sunday at 8 PM IST
    "weekly-review": {
        "task": "app.workers.tasks.reviews.generate_weekly_reviews",
        "schedule": crontab(hour=20, minute=0, day_of_week=0),
    },
    # Monthly report — 1st of every month at 9 AM IST
    "monthly-report": {
        "task": "app.workers.tasks.analytics.generate_monthly_reports",
        "schedule": crontab(hour=9, minute=0, day_of_month=1),
    },
    # Daily plan check — every morning at 7 AM IST
    "daily-plan-check": {
        "task": "app.workers.tasks.notifications.send_daily_plan",
        "schedule": crontab(hour=7, minute=0),
    },
    # Prediction update — every Monday at 6 AM IST
    "update-predictions": {
        "task": "app.workers.tasks.analytics.update_predictions",
        "schedule": crontab(hour=6, minute=0, day_of_week=1),
    },
}
