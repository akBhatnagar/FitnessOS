"""
Coach Agent — the primary user-facing agent and orchestrator.

Responsibilities:
1. Parse and understand the user's request
2. Determine which specialist agents are needed
3. Synthesize all agent outputs into a coherent coaching response
4. Maintain the tone and personality of an elite personal trainer
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from app.agents.base import AgentState, BaseAgent
from app.core.logging import get_logger

logger = get_logger("agent.coach")

COACH_SYSTEM_PROMPT = """You are FitnessOS — an elite AI personal trainer and life coach.

You have worked with this user for years. You know everything about them:
their goals, history, preferences, diet restrictions, injuries, schedule, and upcoming life events.

You are:
- Deeply knowledgeable about exercise science, nutrition, and sports medicine
- Empathetic and encouraging — you never shame or punish
- Data-driven — you use numbers and trends to make decisions
- Adaptive — you adjust plans immediately when life happens
- Long-term focused — every response moves the user toward their goals

Your response should always be:
1. Based on the user's full history and context (retrieved from memory)
2. Actionable and specific — not generic advice
3. Calibrated to where they are TODAY in their journey
4. Aware of upcoming events and deadlines
5. Encouraging without being dishonest

Current User Context:
{user_context}

Today's Date: {current_date}
Days until Pre-Wedding Shoot (Oct 20, 2026): {days_to_pre_wedding}
Days until Wedding (Jan 30, 2027): {days_to_wedding}
Current Phase: {current_phase}
Active Injuries: {injuries}

Recent Progress Summary:
{recent_progress}

Upcoming Events:
{upcoming_events}

Active Goals:
{active_goals}
"""


class CoachAgent(BaseAgent):
    """
    The Coach Agent orchestrates the multi-agent pipeline.

    It is always the first and last agent to run:
    - First: understands the request and decides which agents to invoke
    - Last: synthesizes all outputs into the final response
    """

    name = "coach_agent"
    description = "Primary orchestrator — understands requests, coordinates agents, produces responses"

    @property
    def system_prompt(self) -> str:
        return COACH_SYSTEM_PROMPT

    async def process(self, state: AgentState) -> AgentState:
        """Orchestrate the agent pipeline based on the user's request."""
        self._append_trace(state, "Starting request analysis")

        # Step 1: Inject current date (never hardcoded)
        state["current_date"] = self._get_current_date()

        # Step 2: Analyze the request and decide which agents to call
        routing_decision = await self._route_request(state)
        state.update(routing_decision)

        self._append_trace(state, f"Routing decision: {routing_decision}")
        return state

    async def synthesize_response(self, state: AgentState) -> AgentState:
        """
        Final step: synthesize all agent outputs into a coaching response.

        Called after all specialist agents have contributed their context.
        """
        self._append_trace(state, "Synthesizing final response")

        prompt = self._build_synthesis_prompt(state)
        messages = [
            SystemMessage(content=self._format_system_prompt(state)),
            HumanMessage(content=prompt),
        ]

        response = await self.llm.ainvoke(messages)
        state["final_response"] = response.content

        # Generate follow-up suggestions
        state["follow_up_suggestions"] = await self._generate_follow_ups(state)

        self._append_trace(state, "Response synthesized successfully")
        return state

    async def _route_request(self, state: AgentState) -> dict:
        """
        Analyze the user message and determine which specialist agents are needed.

        Returns a dict of boolean flags for each agent.
        """
        message = state.get("user_message", "").lower()

        # Keyword-based routing (fast path) — LLM-based routing for ambiguous cases
        routing = {
            "needs_workout_agent": any(
                kw in message for kw in [
                    "workout", "gym", "exercise", "training", "lift", "sets", "reps",
                    "push", "pull", "legs", "chest", "back", "shoulder", "bicep",
                    "tricep", "progressive", "overload", "deload",
                ]
            ),
            "needs_nutrition_agent": any(
                kw in message for kw in [
                    "eat", "food", "meal", "diet", "calorie", "protein", "carb",
                    "fat", "macro", "nutrition", "recipe", "cook", "restaurant",
                    "paneer", "whey", "hunger", "weight loss",
                ]
            ),
            "needs_swimming_agent": any(
                kw in message for kw in [
                    "swim", "pool", "lap", "stroke", "freestyle", "breathing",
                    "float", "water",
                ]
            ),
            "needs_analytics_agent": any(
                kw in message for kw in [
                    "progress", "trend", "plateau", "analytic", "report", "chart",
                    "predict", "compare", "how am i doing", "statistics",
                ]
            ),
            "needs_scheduler_agent": any(
                kw in message for kw in [
                    "schedule", "plan", "week", "tomorrow", "today", "missed",
                    "reschedule", "calendar", "routine",
                ]
            ),
            "needs_event_agent": any(
                kw in message for kw in [
                    "wedding", "event", "trip", "travel", "festival", "shoot",
                    "countdown", "deadline", "holiday",
                ]
            ),
            "needs_reflection_agent": any(
                kw in message for kw in [
                    "review", "reflect", "how did i do", "weekly", "last week",
                    "this week", "summary", "report", "improvement", "pattern",
                    "consistency", "score", "grade",
                ]
            ),
        }

        # Always invoke memory and knowledge agents (they run before the coach)
        return routing

    def _format_system_prompt(self, state: AgentState) -> str:
        """Format the system prompt with current context."""
        perm = state.get("permanent_memory", {})
        prefs = perm.get("preferences", {})
        goals = state.get("current_goals", [])
        events = state.get("upcoming_events", [])
        progress = state.get("recent_progress", {})

        pre_wedding_days = self._days_until("2026-10-20")
        wedding_days = self._days_until("2027-01-30")

        return self.system_prompt.format(
            user_context=str(prefs),
            current_date=state.get("current_date", self._get_current_date()),
            days_to_pre_wedding=pre_wedding_days,
            days_to_wedding=wedding_days,
            current_phase=state.get("current_phase", "unknown"),
            injuries=", ".join(state.get("current_injuries", [])) or "None",
            recent_progress=str(progress),
            upcoming_events=str(events),
            active_goals=str(goals),
        )

    def _build_synthesis_prompt(self, state: AgentState) -> str:
        """Build the synthesis prompt combining all agent outputs."""
        parts = [f"User asked: {state.get('user_message', '')}"]

        if state.get("reasoning_plan"):
            parts.append(f"\nReasoning Plan:\n{state['reasoning_plan']}")
        if state.get("workout_context"):
            parts.append(f"\nWorkout Context:\n{state['workout_context']}")
        if state.get("nutrition_context"):
            parts.append(f"\nNutrition Context:\n{state['nutrition_context']}")
        if state.get("swimming_context"):
            parts.append(f"\nSwimming Context:\n{state['swimming_context']}")
        if state.get("analytics_context"):
            parts.append(f"\nAnalytics:\n{state['analytics_context']}")
        if state.get("schedule_context"):
            parts.append(f"\nSchedule:\n{state['schedule_context']}")
        if state.get("event_context"):
            parts.append(f"\nEvent Context:\n{state['event_context']}")
        if state.get("reflection_context"):
            parts.append(f"\nWeekly Reflection:\n{state['reflection_context']}")

        # Include relevant knowledge retrieved by Knowledge Agent
        knowledge = state.get("permanent_memory", {}).get("knowledge_context", [])
        if knowledge:
            excerpts = "\n".join(
                f"- {k.get('content', '')[:200]}" for k in knowledge[:3]
            )
            parts.append(f"\nEvidence-Based Knowledge:\n{excerpts}")

        parts.append(
            "\nUsing all the above context, provide a comprehensive, personalized coaching response. "
            "Be specific, actionable, and encouraging."
        )

        return "\n".join(parts)

    async def _generate_follow_ups(self, state: AgentState) -> list[str]:
        """Generate 3 relevant follow-up questions the user might want to ask."""
        prompt = (
            f"Based on this coaching conversation about: {state.get('user_message', '')}\n"
            "Generate 3 short follow-up questions the user might want to ask next. "
            "Return only the questions, one per line."
        )
        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        lines = [line.strip() for line in response.content.strip().split("\n") if line.strip()]
        return lines[:3]
