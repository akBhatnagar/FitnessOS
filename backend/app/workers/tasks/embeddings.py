"""Embedding generation tasks — runs after new memories are stored."""

from __future__ import annotations

from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger("worker.embeddings")


@celery_app.task(name="app.workers.tasks.embeddings.generate_embedding", bind=True, max_retries=3)
def generate_embedding(self, content: str, user_id: str, source_type: str) -> dict:
    """Generate and store an embedding for a piece of content."""
    import asyncio
    from app.db.session import AsyncSessionLocal
    from app.services.llm.provider import get_embedding_model
    from app.db.models.memory import Embedding
    import uuid

    async def _run():
        model = get_embedding_model()
        vector = model.embed_query(content)
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from app.db.models.user import User
            u = await db.execute(select(User.id).where(User.clerk_user_id == user_id))
            row = u.first()
            if not row:
                return {"status": "user_not_found"}

            record = Embedding(
                user_id=row[0],
                content=content,
                embedding=vector,
                source_type=source_type,
                embedding_model="text-embedding-3-small",
            )
            db.add(record)
            await db.commit()
            return {"status": "ok", "source_type": source_type}

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error("Embedding generation failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)
