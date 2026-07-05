"""Weekly review Celery tasks."""

from __future__ import annotations

from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger("worker.reviews")


@celery_app.task(name="app.workers.tasks.reviews.generate_weekly_reviews", bind=True, max_retries=3)
def generate_weekly_reviews(self) -> dict:
    """
    Generate weekly coaching reports for all active users.

    Runs every Sunday evening. Creates a WeeklyReview record for each user
    and stores coaching insights back into the memory system.
    """
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.session import AsyncSessionLocal
    from app.agents.reflection.agent import ReflectionAgent

    async def _run():
        async with AsyncSessionLocal() as db:
            # Get all active users
            from sqlalchemy import select
            from app.db.models.user import User

            result = await db.execute(
                select(User).where(User.is_active == True)  # noqa: E712
            )
            users = result.scalars().all()

            agent = ReflectionAgent(db)
            reports_generated = 0

            for user in users:
                try:
                    report = await agent.generate_weekly_review(str(user.clerk_user_id))
                    reports_generated += 1
                    logger.info("Weekly review generated", user_id=str(user.id))
                except Exception as exc:
                    logger.error(
                        "Failed to generate review",
                        user_id=str(user.id),
                        error=str(exc),
                    )

            await db.commit()
            return {"reports_generated": reports_generated}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("Weekly review task failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)
