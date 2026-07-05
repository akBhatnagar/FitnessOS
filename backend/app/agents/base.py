"""
Base agent class and shared agent state.

Every FitnessOS agent inherits from BaseAgent and operates on AgentState.
State is passed through the LangGraph graph — agents communicate
exclusively via state, never by direct method calls.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from app.core.logging import get_logger
from app.services.llm.provider import get_llm


class AgentState(TypedDict, total=False):
    """
    Shared state passed between all agents in the LangGraph graph.

    Every agent reads from and writes to this state.
    Fields are optional (total=False) so agents only update their own slice.
    """

    # ---- Request context ----
    user_id: str
    session_id: str
    request_id: str
    user_message: str
    current_date: str  # ISO format, always calculated dynamically

    # ---- Conversation ----
    messages: list[BaseMessage]
    conversation_history: list[dict[str, Any]]

    # ---- Memory retrieval results ----
    permanent_memory: dict[str, Any]  # user profile, preferences
    relevant_memories: list[dict[str, Any]]  # semantically similar memories
    recent_progress: dict[str, Any]  # last 7 days summary
    current_goals: list[dict[str, Any]]
    upcoming_events: list[dict[str, Any]]
    current_injuries: list[str]
    current_phase: str  # hypertrophy, cutting, deload, etc.

    # ---- Agent outputs ----
    reasoning_plan: str
    workout_context: dict[str, Any]
    nutrition_context: dict[str, Any]
    swimming_context: dict[str, Any]
    analytics_context: dict[str, Any]
    schedule_context: dict[str, Any]
    event_context: dict[str, Any]
    reflection_context: dict[str, Any]

    # ---- Final output ----
    final_response: str
    agent_trace: list[str]  # which agents were invoked and why
    confidence_score: float
    follow_up_suggestions: list[str]

    # ---- Control flow ----
    needs_workout_agent: bool
    needs_nutrition_agent: bool
    needs_swimming_agent: bool
    needs_analytics_agent: bool
    needs_scheduler_agent: bool
    needs_event_agent: bool
    needs_reflection_agent: bool
    error: str | None


class BaseAgent(ABC):
    """
    Abstract base class for all FitnessOS agents.

    Subclasses must implement:
    - system_prompt: the agent's role description
    - process: the main agent logic (receives and returns AgentState)
    """

    name: str = "base_agent"
    description: str = "Base agent"

    def __init__(self) -> None:
        self.logger = get_logger(f"agent.{self.name}")
        self._llm: BaseChatModel | None = None

    @property
    def llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = get_llm()
        return self._llm

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the agent's system prompt."""
        ...

    @abstractmethod
    async def process(self, state: AgentState) -> AgentState:
        """
        Process the current state and return an updated state.

        This is the agent's main entry point called by the LangGraph graph.
        Agents must not have side effects beyond updating state and
        persisting relevant data to the database.
        """
        ...

    def _append_trace(self, state: AgentState, message: str) -> None:
        """Add an entry to the agent execution trace for debugging."""
        trace = list(state.get("agent_trace", []))
        timestamp = datetime.utcnow().isoformat()
        trace.append(f"[{timestamp}] {self.name}: {message}")
        state["agent_trace"] = trace

    def _get_current_date(self) -> str:
        """Always return today's date. Never hardcode dates."""
        return date.today().isoformat()

    def _days_until(self, target_date: str | date) -> int:
        """Calculate days until a target date from today."""
        if isinstance(target_date, str):
            target = date.fromisoformat(target_date)
        else:
            target = target_date
        return (target - date.today()).days
