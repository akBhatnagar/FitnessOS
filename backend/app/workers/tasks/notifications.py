"""Daily plan and notification tasks."""

from __future__ import annotations

from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger("worker.notifications")


@celery_app.task(name="app.workers.tasks.notifications.send_daily_plan", bind=True, max_retries=2)
def send_daily_plan(self) -> dict:
    """
    Generate and store today's coaching summary for all active users.

    Runs daily at 7 AM IST. Stores a daily coaching note in memory
    so the first chat of the day has immediate context.
    """
    import asyncio
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import select
    from app.db.models.user import User
    from app.db.models.memory import MemoryStore, MemoryType
    from datetime import date

    async def _run():
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.is_active == True))  # noqa: E712
            users = result.scalars().all()

            today = date.today()
            day_name = today.strftime("%A")
            count = 0

            for user in users:
                try:
                    # Store a daily context note in memory
                    note = MemoryStore(
                        user_id=user.id,
                        memory_type=MemoryType.EPISODIC,
                        category="daily_context",
                        content=(
                            f"Today is {day_name}, {today.isoformat()}. "
                            f"Daily check-in generated at 7 AM IST."
                        ),
                        importance_score=0.3,
                        source_type="system",
                    )
                    db.add(note)
                    count += 1
                except Exception as exc:
                    logger.error("Daily plan note failed", user_id=str(user.id), error=str(exc))

            await db.commit()
            logger.info("Daily plan notes stored", count=count)
            return {"notes_created": count, "date": today.isoformat()}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("Daily plan task failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)
