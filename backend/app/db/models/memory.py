"""
Memory system models: conversations, long-term memory, and vector embeddings.

This is the core of FitnessOS's intelligence — the AI never forgets because
everything is stored and retrieved through these models.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base, TimestampMixin, UUIDMixin


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MemoryType(str, Enum):
    PERMANENT = "permanent"    # rarely changes: preferences, goals, events
    EPISODIC = "episodic"      # conversations, sessions, meals
    SEMANTIC = "semantic"      # learned facts about the user
    PROCEDURAL = "procedural"  # coaching strategies, templates


class ConversationMessage(UUIDMixin, TimestampMixin, Base):
    """
    Full conversation history.

    Every message between the user and any agent is stored permanently.
    The Memory Agent indexes these with embeddings for semantic retrieval.
    """

    __tablename__ = "conversation_history"
    __table_args__ = (
        Index("ix_conv_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    role: Mapped[MessageRole] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String(100))

    # Embedding for semantic search
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dimensions)
    )

    # Metadata about this message
    token_count: Mapped[int | None] = mapped_column(Integer)
    tool_calls: Mapped[dict | None] = mapped_column(JSONB)
    tool_results: Mapped[dict | None] = mapped_column(JSONB)
    message_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    user: Mapped = relationship("User", back_populates="conversations")

    def __repr__(self) -> str:
        return f"<ConversationMessage {self.role} at {self.created_at}>"


class MemoryStore(UUIDMixin, TimestampMixin, Base):
    """
    Long-term memory layer with semantic categorization.

    The Memory Agent continuously extracts and stores facts, preferences,
    corrections, and observations from conversations. Each memory has an
    embedding for semantic retrieval.

    Design principles:
    - Never delete memories (use is_superseded for outdated information)
    - Always timestamp memories for temporal reasoning
    - Tag memories by type for targeted retrieval
    """

    __tablename__ = "memory_store"
    __table_args__ = (
        Index("ix_memory_user_type", "user_id", "memory_type"),
        Index("ix_memory_user_active", "user_id", "is_active"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    memory_type: Mapped[MemoryType] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)

    # Embedding for semantic similarity search
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dimensions)
    )

    importance_score: Mapped[float] = mapped_column(Numeric(3, 2), default=0.5)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superseded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    # Source tracking
    source_type: Mapped[str | None] = mapped_column(String(50))  # conversation, review, manual
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    tags: Mapped[list] = mapped_column(JSONB, default=list)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    user: Mapped = relationship("User", back_populates="memories")

    def __repr__(self) -> str:
        return f"<MemoryStore {self.memory_type.value}/{self.category}: {self.content[:60]}>"


class Embedding(UUIDMixin, TimestampMixin, Base):
    """
    Generic embedding store for any content type.

    Used for RAG over the knowledge base (exercise science, nutrition guides, etc.)
    and for similarity search across all user content.
    """

    __tablename__ = "embeddings"
    __table_args__ = (
        Index("ix_embedding_source", "source_type", "source_id"),
    )

    source_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dimensions), nullable=False
    )
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chunk_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
