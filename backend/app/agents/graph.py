"""
FitnessOS LangGraph Multi-Agent Orchestration Pipeline.

This module defines the agent execution graph. Each node is an agent function.
The graph uses conditional edges to route to specialist agents based on
the Coach Agent's routing decision.

Pipeline execution order:
1. Memory Agent (load context)
2. Knowledge Agent (retrieve domain knowledge)
3. Coach Agent (understand request, decide routing)
4. [Parallel] Specialist agents as needed:
   - Workout Agent
   - Nutrition Agent
   - Swimming Agent
   - Analytics Agent
   - Scheduler Agent
   - Event Agent
5. Coach Agent (synthesize final response)
6. Memory Agent (store new memories)
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentState
from app.agents.coach.agent import CoachAgent
from app.agents.memory.agent import MemoryAgent
from app.agents.knowledge.agent import KnowledgeAgent
from app.agents.workout.agent import WorkoutAgent
from app.agents.nutrition.agent import NutritionAgent
from app.agents.swimming.agent import SwimmingAgent
from app.agents.analytics.agent import AnalyticsAgent
from app.agents.scheduler.agent import SchedulerAgent
from app.agents.event.agent import EventAgent
from app.agents.reflection.agent import ReflectionAgent
from app.core.logging import get_logger

logger = get_logger("agent.graph")


def _route_to_specialists(state: AgentState) -> str:
    """
    Conditional routing function — picks the primary specialist for this request.

    Priority order: Event > Reflection > Scheduler > Workout > Nutrition > Swimming > Analytics
    Sequential routing avoids LangGraph state merge conflicts from parallel execution.
    """
    if state.get("needs_event_agent"):
        return "event_agent"
    if state.get("needs_reflection_agent"):
        return "reflection_agent"
    if state.get("needs_scheduler_agent"):
        return "scheduler_agent"
    if state.get("needs_workout_agent"):
        return "workout_agent"
    if state.get("needs_nutrition_agent"):
        return "nutrition_agent"
    if state.get("needs_swimming_agent"):
        return "swimming_agent"
    if state.get("needs_analytics_agent"):
        return "analytics_agent"
    return "synthesize"


def build_agent_graph(db: AsyncSession) -> StateGraph:
    """
    Build and compile the FitnessOS agent graph.

    The graph is rebuilt per-request because each request gets a fresh
    database session. The graph structure itself is stateless — only
    the AgentState carries request-scoped data.
    """
    # Instantiate agents with their database session
    coach = CoachAgent()
    memory = MemoryAgent(db)
    knowledge = KnowledgeAgent(db)
    workout = WorkoutAgent(db)
    nutrition = NutritionAgent(db)
    swimming = SwimmingAgent(db)
    analytics = AnalyticsAgent(db)
    scheduler = SchedulerAgent(db)
    event = EventAgent(db)
    reflection = ReflectionAgent(db)

    graph = StateGraph(AgentState)

    # ---- Node definitions ----
    graph.add_node("memory_load", memory.process)
    graph.add_node("knowledge_retrieve", knowledge.process)
    graph.add_node("coach_route", coach.process)
    graph.add_node("workout_agent", workout.process)
    graph.add_node("nutrition_agent", nutrition.process)
    graph.add_node("swimming_agent", swimming.process)
    graph.add_node("analytics_agent", analytics.process)
    graph.add_node("scheduler_agent", scheduler.process)
    graph.add_node("event_agent", event.process)
    graph.add_node("reflection_agent", reflection.process)
    graph.add_node("synthesize", coach.synthesize_response)
    graph.add_node("memory_store", memory.store_conversation_memory)

    # ---- Edge definitions ----

    # Entry: always load memory and knowledge first
    graph.add_edge(START, "memory_load")
    graph.add_edge("memory_load", "knowledge_retrieve")
    graph.add_edge("knowledge_retrieve", "coach_route")

    # Route to exactly one specialist (sequential, avoids state merge conflicts)
    graph.add_conditional_edges(
        "coach_route",
        _route_to_specialists,
        {
            "workout_agent": "workout_agent",
            "nutrition_agent": "nutrition_agent",
            "swimming_agent": "swimming_agent",
            "analytics_agent": "analytics_agent",
            "scheduler_agent": "scheduler_agent",
            "event_agent": "event_agent",
            "reflection_agent": "reflection_agent",
            "synthesize": "synthesize",
        },
    )

    # Each specialist flows into synthesis
    for specialist in [
        "workout_agent",
        "nutrition_agent",
        "swimming_agent",
        "analytics_agent",
        "scheduler_agent",
        "event_agent",
        "reflection_agent",
    ]:
        graph.add_edge(specialist, "synthesize")

    # After synthesis, store memories then end
    graph.add_edge("synthesize", "memory_store")
    graph.add_edge("memory_store", END)

    return graph.compile()


NODE_STATUS_MESSAGES: dict[str, str] = {
    "memory_load": "Reviewing your history…",
    "knowledge_retrieve": "Researching relevant knowledge…",
    "coach_route": "Understanding your request…",
    "workout_agent": "Working on your training…",
    "nutrition_agent": "Analyzing nutrition…",
    "swimming_agent": "Planning swim guidance…",
    "analytics_agent": "Looking at your progress…",
    "scheduler_agent": "Checking your schedule…",
    "event_agent": "Considering upcoming events…",
    "reflection_agent": "Reflecting on your week…",
    "synthesize": "Putting it all together…",
    "memory_store": "Saving insights…",
}


def _initial_agent_state(
    user_message: str,
    user_id: str,
    session_id: str,
    request_id: str | None = None,
) -> AgentState:
    import uuid
    from datetime import date

    return {
        "user_id": user_id,
        "session_id": session_id,
        "request_id": request_id or str(uuid.uuid4()),
        "user_message": user_message,
        "current_date": date.today().isoformat(),
        "messages": [],
        "conversation_history": [],
        "agent_trace": [],
        "error": None,
    }


async def run_agent_pipeline(
    user_message: str,
    user_id: str,
    session_id: str,
    db: AsyncSession,
    request_id: str | None = None,
) -> AgentState:
    """
    Execute the full multi-agent pipeline for a user message.

    This is the main entry point called by the API route.
    """
    initial_state = _initial_agent_state(user_message, user_id, session_id, request_id)

    logger.info(
        "Starting agent pipeline",
        user_id=user_id,
        session_id=session_id,
        message_length=len(user_message),
    )

    graph = build_agent_graph(db)

    try:
        final_state = await graph.ainvoke(initial_state)
        logger.info(
            "Agent pipeline completed",
            agents_invoked=len(final_state.get("agent_trace", [])),
        )
        return final_state
    except Exception as exc:
        logger.error("Agent pipeline failed", error=str(exc), user_id=user_id)
        initial_state["error"] = str(exc)
        initial_state["final_response"] = (
            "I encountered an issue processing your request. Please try again."
        )
        return initial_state


async def stream_agent_pipeline(
    user_message: str,
    user_id: str,
    session_id: str,
    db: AsyncSession,
    request_id: str | None = None,
):
    """
    Stream pipeline progress as each graph node finishes.

    Yields dict events:
      - {"type": "status", "node": str, "message": str}
      - {"type": "heartbeat"}
      - {"type": "done", "state": AgentState}
      - {"type": "error", "message": str, "state": AgentState}
    """
    import asyncio

    initial_state = _initial_agent_state(user_message, user_id, session_id, request_id)
    logger.info(
        "Starting streaming agent pipeline",
        user_id=user_id,
        session_id=session_id,
        message_length=len(user_message),
    )

    graph = build_agent_graph(db)
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def _run() -> None:
        final_state: AgentState = initial_state
        try:
            async for mode, chunk in graph.astream(
                initial_state,
                stream_mode=["updates", "values"],
            ):
                if mode == "updates" and isinstance(chunk, dict):
                    for node_name in chunk:
                        await queue.put(
                            {
                                "type": "status",
                                "node": node_name,
                                "message": NODE_STATUS_MESSAGES.get(
                                    node_name, "Working on it…"
                                ),
                            }
                        )
                elif mode == "values" and isinstance(chunk, dict):
                    final_state = chunk  # type: ignore[assignment]
            await queue.put({"type": "done", "state": final_state})
        except Exception as exc:
            logger.error("Streaming agent pipeline failed", error=str(exc), user_id=user_id)
            initial_state["error"] = str(exc)
            initial_state["final_response"] = (
                "I encountered an issue processing your request. Please try again."
            )
            await queue.put(
                {
                    "type": "error",
                    "message": str(exc),
                    "state": initial_state,
                }
            )
        finally:
            await queue.put(None)

    task = asyncio.create_task(_run())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=12.0)
            except asyncio.TimeoutError:
                yield {"type": "heartbeat"}
                continue
            if item is None:
                break
            yield item
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
