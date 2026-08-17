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
from datetime import date, datetime, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentState, BaseAgent
from app.db.models.memory import MemoryStore, MemoryType, ConversationMessage, MessageRole
from app.db.models.user import User, UserPreferences
from app.db.models.goal import Goal, GoalStatus
from app.db.models.event import Event
from app.db.models.workout import WorkoutSession, SessionStatus
from app.db.models.nutrition import Meal
from app.db.models.measurement import Measurement
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

        permanent = await self._load_permanent_memory(user_id)
        goals = await self._load_active_goals(user_id)
        events = await self._load_upcoming_events(user_id)
        relevant = await self._retrieve_relevant_memories(
            user_id, state.get("user_message", "")
        )
        recent_progress = await self._load_recent_progress(user_id)
        conversation_history = await self._load_conversation_history(
            user_id, state.get("session_id", "")
        )

        state["permanent_memory"] = permanent
        state["current_goals"] = goals
        state["upcoming_events"] = events
        state["relevant_memories"] = relevant
        state["recent_progress"] = recent_progress
        state["conversation_history"] = conversation_history
        state["current_injuries"] = permanent.get("preferences", {}).get("current_injuries", [])
        state["current_phase"] = permanent.get("current_phase", "hypertrophy")

        self._append_trace(state, f"Loaded {len(relevant)} relevant memories, {len(conversation_history)} prior messages")
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

    async def _load_recent_progress(self, user_id: str) -> dict[str, Any]:
        """
        Always-on: load last 7 days of workouts, nutrition, and weight measurements.

        This ensures the Coach LLM always has real data regardless of which
        specialist agent is routed to.
        """
        u = await self.db.execute(select(User.id).where(User.clerk_user_id == user_id))
        user_row = u.first()
        if not user_row:
            return {}
        uid = user_row[0]

        today = date.today()
        week_start = today - timedelta(days=7)

        # --- Gym sessions (last 7 days) ---
        sessions_result = await self.db.execute(
            select(WorkoutSession).where(
                WorkoutSession.user_id == uid,
                WorkoutSession.scheduled_date >= week_start,
            ).order_by(WorkoutSession.scheduled_date.desc())
        )
        sessions = sessions_result.scalars().all()
        gym_planned = len(sessions)
        gym_completed = sum(1 for s in sessions if s.status == SessionStatus.COMPLETED)
        completed_sessions = [
            {"date": s.scheduled_date.isoformat(), "name": s.session_name}
            for s in sessions
            if s.status == SessionStatus.COMPLETED
        ]

        # --- Nutrition (last 7 days) ---
        meals_result = await self.db.execute(
            select(Meal).where(
                Meal.user_id == uid,
                Meal.meal_date >= week_start,
            )
        )
        meals = meals_result.scalars().all()
        days_with_logs = len({m.meal_date for m in meals}) or 1
        total_cals = sum(float(m.total_calories or 0) for m in meals)
        total_protein = sum(float(m.total_protein_g or 0) for m in meals)
        total_carbs = sum(float(m.total_carbs_g or 0) for m in meals)
        total_fat = sum(float(m.total_fat_g or 0) for m in meals)

        # --- Weight measurements (last 10 entries) ---
        meas_result = await self.db.execute(
            select(Measurement).where(
                Measurement.user_id == uid,
                Measurement.weight_kg.isnot(None),
            ).order_by(Measurement.measured_on.desc()).limit(10)
        )
        measurements = meas_result.scalars().all()
        weight_history = [
            {"date": m.measured_on.isoformat(), "weight_kg": float(m.weight_kg)}
            for m in measurements
        ]

        return {
            "last_7_days": {
                "gym_sessions_planned": gym_planned,
                "gym_sessions_completed": gym_completed,
                "gym_adherence_pct": round(gym_completed / gym_planned * 100) if gym_planned else 0,
                "completed_sessions": completed_sessions,
                "nutrition_days_logged": days_with_logs if meals else 0,
                "avg_daily_calories": round(total_cals / days_with_logs) if meals else 0,
                "avg_daily_protein_g": round(total_protein / days_with_logs) if meals else 0,
                "avg_daily_carbs_g": round(total_carbs / days_with_logs) if meals else 0,
                "avg_daily_fat_g": round(total_fat / days_with_logs) if meals else 0,
            },
            "weight_history": weight_history,
        }

    async def _load_conversation_history(
        self, user_id: str, session_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Load recent messages from the current session to maintain context."""
        if not session_id:
            return []
        try:
            session_uuid = uuid.UUID(session_id)
        except (ValueError, AttributeError):
            return []

        result = await self.db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.session_id == session_uuid)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        messages = result.scalars().all()
        return [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in reversed(messages)
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
