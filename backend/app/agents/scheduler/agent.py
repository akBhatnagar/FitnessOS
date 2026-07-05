"""Scheduler Agent — daily/weekly plan management and rescheduling."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentState, BaseAgent
from app.db.models.user import User
from app.db.models.workout import WorkoutSession, SessionStatus
from app.db.models.event import Event
from app.core.logging import get_logger

logger = get_logger("agent.scheduler")

USER_SCHEDULE = {
    "work_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    "work_hours": "10:30 AM – 8:00 PM",
    "swim_time": "8:00 AM (morning)",
    "gym_time": "9:00 PM – 10:00 PM",
    "weekend": "Recovery-focused (light activity only)",
    "sleep_goal": "12:00 AM bedtime (currently 3:00 AM)",
    "wake_goal": "7:00 AM (currently 10:00 AM)",
}

WEEKLY_TEMPLATE = {
    "Monday": {"gym": "Push (Chest, Shoulders, Triceps)", "swim": True},
    "Tuesday": {"gym": "Pull (Back, Biceps)", "swim": True},
    "Wednesday": {"gym": "Legs + Core", "swim": False, "note": "No swim — recovery priority"},
    "Thursday": {"gym": "Push (Volume)", "swim": True},
    "Friday": {"gym": "Pull (Volume)", "swim": True},
    "Saturday": {"gym": None, "swim": False, "note": "Active recovery — light walk or yoga"},
    "Sunday": {"gym": "Legs (if energy allows)", "swim": False, "note": "Weekly review day"},
}


class SchedulerAgent(BaseAgent):
    name = "scheduler_agent"
    description = "Maintains daily/weekly plans, rebuilds after missed sessions, optimizes recovery"

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db

    @property
    def system_prompt(self) -> str:
        return """You are an expert fitness scheduler and recovery optimizer.

Core principles:
1. Recovery is sacred — never schedule two heavy sessions back-to-back
2. When sessions are missed, REDISTRIBUTE intelligently — never punish
3. Always account for the user's actual schedule (office 10:30AM-8PM, swim 8AM, gym 9PM)
4. Weekends are recovery-focused unless a special event requires otherwise
5. Optimize sleep gradually: 3AM → 2AM → 1AM → 12AM over 8 weeks
6. Calculate all dates dynamically — never hardcode

Rescheduling logic when a session is missed:
- Missed Monday Push → Add shoulder isolation to Thursday
- Missed gym entirely → Add 15 min LISS cardio to that day instead  
- Missed swim → Don't make up — maintain frequency over volume
- Travel/illness → Reduce volume 40%, maintain frequency
- Never stack more than 3 gym sessions in a row"""

    async def process(self, state: AgentState) -> AgentState:
        if not state.get("needs_scheduler_agent"):
            return state

        self._append_trace(state, "Building schedule context")
        user_id = state.get("user_id", "")

        missed = await self._get_missed_sessions(user_id)
        this_week = await self._get_this_week_sessions(user_id)
        upcoming_events = state.get("upcoming_events", [])

        schedule_context = await self._generate_schedule_response(
            state, this_week, missed, upcoming_events
        )
        state["schedule_context"] = schedule_context
        self._append_trace(state, f"Schedule built — {len(missed)} missed sessions found")
        return state

    async def rebuild_week(
        self,
        user_id: str,
        missed_sessions: list[dict],
        remaining_days: list[date],
        events: list[dict],
    ) -> dict[str, Any]:
        """Rebuild the remaining week's schedule after missed sessions."""
        prompt = f"""Rebuild the training schedule for the remaining days this week.

Missed sessions: {json.dumps(missed_sessions)}
Remaining days: {[d.isoformat() for d in remaining_days]}
Upcoming events: {json.dumps(events)}

Base weekly template:
{json.dumps(WEEKLY_TEMPLATE, indent=2)}

User schedule constraints:
{json.dumps(USER_SCHEDULE, indent=2)}

Create a realistic, recoverable schedule that:
1. Doesn't punish the user
2. Maximizes remaining progress
3. Respects recovery between sessions
4. Accounts for the 9PM gym slot and 8AM swim slot"""

        response = await self.llm.ainvoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ])
        return {
            "rebuilt_schedule": response.content,
            "missed_sessions": missed_sessions,
            "remaining_days": [d.isoformat() for d in remaining_days],
        }

    async def _get_this_week_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """Load this week's planned and completed sessions from the DB."""
        u = await self.db.execute(
            select(User.id).where(User.clerk_user_id == user_id)
        )
        user_row = u.first()
        if not user_row:
            return []

        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # Monday
        week_end = week_start + timedelta(days=6)

        result = await self.db.execute(
            select(WorkoutSession).where(
                WorkoutSession.user_id == user_row[0],
                WorkoutSession.scheduled_date >= week_start,
                WorkoutSession.scheduled_date <= week_end,
            ).order_by(WorkoutSession.scheduled_date)
        )
        sessions = result.scalars().all()
        return [
            {
                "date": s.scheduled_date.isoformat(),
                "day": s.scheduled_date.strftime("%A"),
                "type": s.session_name,
                "status": str(s.status),
                "duration_min": s.duration_minutes,
            }
            for s in sessions
        ]

    async def _get_missed_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """Find sessions that were planned but not completed in the past 7 days."""
        u = await self.db.execute(
            select(User.id).where(User.clerk_user_id == user_id)
        )
        user_row = u.first()
        if not user_row:
            return []

        today = date.today()
        week_ago = today - timedelta(days=7)

        result = await self.db.execute(
            select(WorkoutSession).where(
                WorkoutSession.user_id == user_row[0],
                WorkoutSession.scheduled_date >= week_ago,
                WorkoutSession.scheduled_date < today,
                WorkoutSession.status.notin_([SessionStatus.COMPLETED, SessionStatus.IN_PROGRESS]),
            ).order_by(WorkoutSession.scheduled_date)
        )
        missed = result.scalars().all()
        return [
            {
                "date": s.scheduled_date.isoformat(),
                "day": s.scheduled_date.strftime("%A"),
                "type": s.session_name,
                "reason": str(s.status),
            }
            for s in missed
        ]

    async def _generate_schedule_response(
        self,
        state: AgentState,
        this_week: list[dict],
        missed: list[dict],
        events: list[dict],
    ) -> dict[str, Any]:
        today = date.today()
        remaining_days = [
            today + timedelta(days=i)
            for i in range(1, 7 - today.weekday())
        ]

        prompt = f"""Schedule question: {state.get('user_message', '')}

Today: {today.isoformat()} ({today.strftime('%A')})

This week's sessions:
{json.dumps(this_week, indent=2) if this_week else "No sessions logged yet this week"}

Missed sessions (past 7 days):
{json.dumps(missed, indent=2) if missed else "No missed sessions — great consistency!"}

Remaining days this week: {[d.strftime('%A %b %d') for d in remaining_days]}

Upcoming events: {json.dumps(events, indent=2) if events else "None"}

Standard weekly template:
{json.dumps(WEEKLY_TEMPLATE, indent=2)}

User's fixed schedule:
- Gym: 9PM (Mon-Sun if planned)
- Swim: 8AM (Mon, Tue, Thu, Fri)
- Work: 10:30AM-8PM (Mon-Fri)
- Weekend: Recovery focus

Answer the scheduling question with specific day-by-day recommendations.
If sessions were missed, show how to adapt the remaining week without punishment."""

        response = await self.llm.ainvoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ])

        return {
            "analysis": response.content,
            "this_week_sessions": this_week,
            "missed_sessions": missed,
            "remaining_days": [d.isoformat() for d in remaining_days],
            "weekly_template": WEEKLY_TEMPLATE,
        }
