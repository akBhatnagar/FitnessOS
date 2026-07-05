"""
Memory repository — all DB operations for ConversationHistory, MemoryStore, and Embeddings.

The vector similarity search uses pgvector's <=> cosine distance operator.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import and_, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.memory import ConversationMessage, MemoryStore, Embedding
from app.repositories.base import BaseRepository


class MemoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ─── Conversation History ───────────────────────────────────────────────

    async def save_message(
        self,
        user_id: UUID,
        session_id: str,
        role: str,
        content: str,
        agent_trace: list[str] | None = None,
        token_count: int | None = None,
    ) -> ConversationMessage:
        msg = ConversationMessage(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            agent_trace=agent_trace or [],
            token_count=token_count,
        )
        self.db.add(msg)
        await self.db.flush()
        return msg

    async def get_session_history(
        self,
        user_id: UUID,
        session_id: str,
        limit: int = 20,
    ) -> Sequence[ConversationMessage]:
        result = await self.db.execute(
            select(ConversationMessage)
            .where(
                ConversationMessage.user_id == user_id,
                ConversationMessage.session_id == session_id,
            )
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return list(reversed(rows))

    async def get_recent_conversations(
        self,
        user_id: UUID,
        limit: int = 50,
    ) -> Sequence[ConversationMessage]:
        result = await self.db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.user_id == user_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    # ─── Memory Store (semantic facts) ─────────────────────────────────────

    async def save_memory(
        self,
        user_id: UUID,
        memory_type: str,
        category: str,
        content: str,
        importance_score: float = 0.5,
        source: str = "conversation",
        extra: dict | None = None,
    ) -> MemoryStore:
        memory = MemoryStore(
            user_id=user_id,
            memory_type=memory_type,
            category=category,
            content=content,
            importance_score=importance_score,
            source=source,
            extra=extra or {},
        )
        self.db.add(memory)
        await self.db.flush()
        return memory

    async def get_memories_by_type(
        self,
        user_id: UUID,
        memory_type: str,
        limit: int = 20,
    ) -> Sequence[MemoryStore]:
        result = await self.db.execute(
            select(MemoryStore)
            .where(
                MemoryStore.user_id == user_id,
                MemoryStore.memory_type == memory_type,
            )
            .order_by(desc(MemoryStore.importance_score))
            .limit(limit)
        )
        return result.scalars().all()

    async def get_permanent_memories(self, user_id: UUID) -> Sequence[MemoryStore]:
        """Permanent = facts that rarely change (preferences, injuries, goals)."""
        return await self.get_memories_by_type(user_id, "permanent", limit=30)

    async def get_recent_episodic_memories(
        self,
        user_id: UUID,
        limit: int = 10,
    ) -> Sequence[MemoryStore]:
        """Episodic = recent events (workouts done, meals logged, sleep)."""
        result = await self.db.execute(
            select(MemoryStore)
            .where(
                MemoryStore.user_id == user_id,
                MemoryStore.memory_type == "episodic",
            )
            .order_by(desc(MemoryStore.created_at))
            .limit(limit)
        )
        return result.scalars().all()

    # ─── Vector Embeddings (semantic search via pgvector) ──────────────────

    async def save_embedding(
        self,
        user_id: UUID,
        content: str,
        embedding: list[float],
        content_type: str,
        source_id: UUID | None = None,
        extra: dict | None = None,
    ) -> Embedding:
        record = Embedding(
            user_id=user_id,
            content=content,
            embedding=embedding,
            content_type=content_type,
            source_id=source_id,
            extra=extra or {},
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def search_similar(
        self,
        user_id: UUID,
        query_embedding: list[float],
        limit: int = 10,
        similarity_threshold: float = 0.75,
        content_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find semantically similar content using cosine similarity.

        Returns list of dicts with {content, similarity, content_type, created_at}.
        """
        embedding_str = f"[{','.join(str(v) for v in query_embedding)}]"

        conditions = [
            f"user_id = '{user_id}'",
            f"1 - (embedding <=> '{embedding_str}'::vector) >= {similarity_threshold}",
        ]
        if content_types:
            types_str = ", ".join(f"'{t}'" for t in content_types)
            conditions.append(f"content_type IN ({types_str})")

        where_clause = " AND ".join(conditions)

        stmt = text(f"""
            SELECT
                content,
                content_type,
                extra,
                created_at,
                1 - (embedding <=> '{embedding_str}'::vector) AS similarity
            FROM embeddings
            WHERE {where_clause}
            ORDER BY similarity DESC
            LIMIT {limit}
        """)

        result = await self.db.execute(stmt)
        rows = result.mappings().all()

        return [
            {
                "content": row["content"],
                "content_type": row["content_type"],
                "extra": row["extra"],
                "similarity": float(row["similarity"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
