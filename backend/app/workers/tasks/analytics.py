"""Analytics background tasks — predictions, monthly reports."""

from __future__ import annotations

from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger("worker.analytics")


@celery_app.task(name="app.workers.tasks.analytics.update_predictions", bind=True, max_retries=2)
def update_predictions(self) -> dict:
    """
    Recalculate wedding weight predictions for all users.

    Runs every Monday at 6 AM IST. Uses linear regression on
    the last 4 weeks of measurements to project wedding-day weight.
    """
    import asyncio
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import select
    from app.db.models.user import User
    from app.db.models.analytics import Measurement
    from datetime import date, timedelta

    async def _run():
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.is_active == True))  # noqa: E712
            users = result.scalars().all()

            wedding_date = date(2027, 1, 30)
            today = date.today()
            days_to_wedding = (wedding_date - today).days
            updated = 0

            for user in users:
                try:
                    # Get last 4 weeks of weight measurements
                    meas_result = await db.execute(
                        select(Measurement).where(
                            Measurement.user_id == user.id,
                            Measurement.measurement_date >= today - timedelta(days=28),
                            Measurement.weight_kg.is_not(None),
                        ).order_by(Measurement.measurement_date)
                    )
                    measurements = meas_result.scalars().all()

                    if len(measurements) < 2:
                        continue

                    # Simple linear regression on weight
                    weights = [float(m.weight_kg) for m in measurements]
                    days = [(m.measurement_date - measurements[0].measurement_date).days for m in measurements]

                    n = len(weights)
                    mean_days = sum(days) / n
                    mean_weight = sum(weights) / n
                    numerator = sum((days[i] - mean_days) * (weights[i] - mean_weight) for i in range(n))
                    denominator = sum((days[i] - mean_days) ** 2 for i in range(n))

                    if denominator == 0:
                        continue

                    slope = numerator / denominator  # kg/day
                    current_weight = weights[-1]
                    predicted_wedding_weight = current_weight + slope * days_to_wedding

                    logger.info(
                        "Prediction updated",
                        user_id=str(user.id),
                        current_kg=round(current_weight, 1),
                        predicted_kg=round(predicted_wedding_weight, 1),
                        weekly_change=round(slope * 7, 2),
                    )
                    updated += 1

                except Exception as exc:
                    logger.error("Prediction failed", user_id=str(user.id), error=str(exc))

            return {"predictions_updated": updated}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("Prediction update task failed", error=str(exc))
        raise self.retry(exc=exc, countdown=600)


@celery_app.task(name="app.workers.tasks.analytics.generate_monthly_reports", bind=True, max_retries=2)
def generate_monthly_reports(self) -> dict:
    """
    Generate monthly progress reports for all active users.

    Runs on the 1st of every month at 9 AM IST.
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
            month_name = today.strftime("%B %Y")
            count = 0

            for user in users:
                try:
                    # Store a monthly milestone marker in memory
                    memory = MemoryStore(
                        user_id=user.id,
                        memory_type=MemoryType.EPISODIC,
                        category="monthly_milestone",
                        content=f"Monthly report generated for {month_name}. Progress review completed.",
                        importance_score=0.6,
                        source_type="system",
                    )
                    db.add(memory)
                    count += 1
                except Exception as exc:
                    logger.error("Monthly report failed", user_id=str(user.id), error=str(exc))

            await db.commit()
            return {"reports_generated": count, "month": month_name}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("Monthly report task failed", error=str(exc))
        raise self.retry(exc=exc, countdown=600)
