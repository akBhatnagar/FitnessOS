"""
Memory Agent — responsible for all memory operations.

Responsibilities:
1. Load permanent memory (user profile, preferences) before every response
2. Retrieve semantically relevant memories using vector similarity
3. Store new memories extracted from the conversation
4. Summarize and compress old memories to prevent context bloat
5. Update memory importance scores based on access patterns
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentState, BaseAgent
from app.db.models.memory import MemoryStore, MemoryType, ConversationMessage, MessageRole
from app.db.models.user import User, UserPreferences
from app.db.models.goal import Goal, GoalStatus
from app.db.models.event import Event
from app.services.llm.provider import get_embedding_model
from app.core.logging import get_logger

logger = get_logger("agent.memory")


MEMORY_EXTRACTION_PROMPT = """You are analyzing a conversation to extract memorable facts about the user.

Extract facts that should be remembered long-term. Focus on:
- Personal preferences (food, exercise, timing)
- Corrections ("I don't like X", "I prefer Y")
- Goals and motivations
- Physical facts (injuries, conditions)
- Lifestyle information (schedule changes, life events)
- Progress milestones

For each fact, output JSON:
{
  "facts": [
    {
      "category": "diet|exercise|schedule|lifestyle|medical|motivation|milestone",
      "content": "The fact to remember",
      "importance": 0.1-1.0,
      "memory_type": "permanent|episodic|semantic|procedural"
    }
  ]
}

Conversation:
{conversation}
"""


class MemoryAgent(BaseAgent):
    """
    The Memory Agent ensures the AI never forgets anything important.

    It runs at the START of every request (to load context) and at the
    END of every request (to store new information).
    """

    name = "memory_agent"
    description = "Manages all memory: loads context, stores new facts, retrieves relevant memories"

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db
        self.embedding_model = get_embedding_model()

    @property
    def system_prompt(self) -> str:
        return "You are the memory management system for FitnessOS."

    async def process(self, state: AgentState) -> AgentState:
        """Load all relevant memory before the coaching response."""
        user_id = state.get("user_id", "")

        self._append_trace(state, "Loading memory context")

        # Run all retrievals in parallel for performance
        permanent = await self._load_permanent_memory(user_id)
        goals = await self._load_active_goals(user_id)
        events = await self._load_upcoming_events(user_id)
        relevant = await self._retrieve_relevant_memories(
            user_id, state.get("user_message", "")
        )

        state["permanent_memory"] = permanent
        state["current_goals"] = goals
        state["upcoming_events"] = events
        state["relevant_memories"] = relevant
        state["current_injuries"] = permanent.get("preferences", {}).get("current_injuries", [])
        state["current_phase"] = permanent.get("current_phase", "hypertrophy")

        self._append_trace(state, f"Loaded {len(relevant)} relevant memories")
        return state

    async def store_conversation_memory(self, state: AgentState) -> None:
        """
        Extract and store memories from the completed conversation.

        Called after the final response is generated.
        """
        conversation_text = self._format_conversation(state)
        if not conversation_text:
            return

        facts = await self._extract_facts(conversation_text)
        user_id = uuid.UUID(state.get("user_id", ""))

        for fact in facts:
            embedding = await self._embed_text(fact["content"])
            memory = MemoryStore(
                user_id=user_id,
                memory_type=MemoryType(fact.get("memory_type", "semantic")),
                category=fact["category"],
                content=fact["content"],
                importance_score=fact.get("importance", 0.5),
                embedding=embedding,
                source_type="conversation",
                source_id=uuid.UUID(state.get("session_id", str(uuid.uuid4()))),
            )
            self.db.add(memory)

        await self.db.flush()
        logger.info("Stored conversation memories", count=len(facts))

    async def _load_permanent_memory(self, user_id: str) -> dict[str, Any]:
        """Load the user's permanent profile and preferences."""
        result = await self.db.execute(
            select(User, UserPreferences)
            .outerjoin(UserPreferences, User.id == UserPreferences.user_id)
            .where(User.clerk_user_id == user_id)
        )
        row = result.first()
        if not row:
            return {}

        user, prefs = row
        data: dict[str, Any] = {
            "user": {
                "id": str(user.id),
                "name": user.full_name,
                "email": user.email,
                "timezone": user.timezone,
            }
        }

        if prefs:
            data["preferences"] = {
                "diet_type": prefs.diet_type,
                "allowed_foods": prefs.allowed_foods,
                "disallowed_foods": prefs.disallowed_foods,
                "supplement_preferences": prefs.supplement_preferences,
                "work_start_time": str(prefs.work_start_time),
                "work_end_time": str(prefs.work_end_time),
                "gym_preferred_time": str(prefs.gym_preferred_time),
                "current_injuries": prefs.current_injuries,
                "activity_level": prefs.activity_level,
                "motivation_triggers": prefs.motivation_triggers,
                "height_cm": float(prefs.height_cm) if prefs.height_cm else None,
                "current_weight_kg": float(prefs.current_weight_kg) if prefs.current_weight_kg else None,
                "target_weight_kg": float(prefs.target_weight_kg) if prefs.target_weight_kg else None,
            }

        return data

    async def _load_active_goals(self, user_id: str) -> list[dict[str, Any]]:
        """Load all active goals, ordered by priority."""
        result = await self.db.execute(
            select(Goal)
            .join(User, Goal.user_id == User.id)
            .where(User.clerk_user_id == user_id, Goal.status == GoalStatus.ACTIVE)
            .order_by(Goal.priority)
        )
        goals = result.scalars().all()
        return [
            {
                "category": g.category,
                "title": g.title,
                "target_value": float(g.target_value) if g.target_value else None,
                "current_value": float(g.current_value) if g.current_value else None,
                "unit": g.unit,
                "target_date": g.target_date.isoformat() if g.target_date else None,
                "priority": g.priority,
            }
            for g in goals
        ]

    async def _load_upcoming_events(self, user_id: str) -> list[dict[str, Any]]:
        """Load upcoming events, ordered by proximity."""
        today = date.today()
        result = await self.db.execute(
            select(Event)
            .join(User, Event.user_id == User.id)
            .where(
                User.clerk_user_id == user_id,
                Event.is_active == True,  # noqa: E712
                Event.event_date >= today,
            )
            .order_by(Event.event_date)
        )
        events = result.scalars().all()
        return [
            {
                "type": e.event_type,
                "title": e.title,
                "date": e.event_date.isoformat(),
                "days_remaining": e.days_remaining,
                "is_critical": e.is_critical,
                "peak_priority": e.peak_priority,
            }
            for e in events
        ]

    async def _retrieve_relevant_memories(
        self, user_id: str, query: str, top_k: int = 10
    ) -> list[dict[str, Any]]:
        """
        Retrieve the most semantically relevant memories using vector similarity.

        Uses pgvector's cosine distance for efficient approximate nearest neighbor search.
        """
        if not query:
            return []

        query_embedding = await self._embed_text(query)

        # Stringify the vector for pgvector — asyncpg cannot serialize list[float] directly
        vec_str = f"[{','.join(str(v) for v in query_embedding)}]"

        from app.core.config import settings as cfg
        threshold = cfg.memory_similarity_threshold

        sql = text(f"""
            SELECT ms.content, ms.category, ms.memory_type, ms.importance_score,
                   1 - (ms.embedding <=> '{vec_str}'::vector) AS similarity
            FROM memory_store ms
            JOIN users u ON ms.user_id = u.id
            WHERE u.clerk_user_id = :user_id
              AND ms.is_active = true
              AND ms.is_superseded = false
              AND 1 - (ms.embedding <=> '{vec_str}'::vector) > :threshold
            ORDER BY ms.embedding <=> '{vec_str}'::vector
            LIMIT :top_k
        """)

        result = await self.db.execute(
            sql,
            {
                "user_id": user_id,
                "threshold": threshold,
                "top_k": top_k,
            },
        )
        rows = result.fetchall()
        return [
            {
                "content": row.content,
                "category": row.category,
                "memory_type": row.memory_type,
                "importance": float(row.importance_score),
                "similarity": float(row.similarity),
            }
            for row in rows
        ]

    async def _embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text."""
        embeddings = self.embedding_model.embed_documents([text])
        return embeddings[0]

    async def _extract_facts(self, conversation: str) -> list[dict[str, Any]]:
        """Use the LLM to extract memorable facts from a conversation."""
        import json

        prompt = MEMORY_EXTRACTION_PROMPT.format(conversation=conversation)
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])

        try:
            data = json.loads(response.content)
            return data.get("facts", [])
        except (json.JSONDecodeError, KeyError):
            logger.warning("Failed to parse memory extraction response")
            return []

    def _format_conversation(self, state: AgentState) -> str:
        """Format the conversation history for memory extraction."""
        messages = state.get("messages", [])
        return "\n".join(
            f"{msg.type.upper()}: {msg.content}" for msg in messages
        )
