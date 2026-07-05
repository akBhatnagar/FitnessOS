"""Event Agent — milestone-aware training adjustments."""

from __future__ import annotations

from datetime import date
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentState, BaseAgent
from app.db.models.user import User
from app.db.models.event import Event
from app.core.logging import get_logger

logger = get_logger("agent.event")


PHASE_PLAYBOOK = {
    "peak_week": {
        "description": "PEAK WEEK — event in ≤7 days",
        "diet_protocol": "High carb refeed Monday-Wednesday, moderate Thursday-Friday, show-ready Saturday-Sunday. Drop sodium. Increase potassium (banana, coconut water). No new foods.",
        "training": "Full-body pump session Mon. Active recovery only rest of week. No heavy compound lifts.",
        "hydration": "Increase to 4-5L/day Monday-Wednesday, then taper to 2.5L the day before.",
        "sleep": "Prioritize 8h. Dark room. Magnesium at night.",
        "mindset": "You've done the work. Trust the process. This week is about optimization, not improvement.",
    },
    "deload_and_peak_prep": {
        "description": "DELOAD + PEAK PREP — event in 8-14 days",
        "diet_protocol": "Reduce calories by 10%. Maximize anti-inflammatory foods (turmeric, ginger, leafy greens). Minimize processed foods and sodium.",
        "training": "Reduce volume by 40%. Keep intensity high. Focus on form. No new exercises.",
        "hydration": "3L/day minimum. Electrolytes after gym.",
        "sleep": "Non-negotiable 7.5h. This is where recovery happens.",
        "mindset": "The competition starts now. Every sleep, meal, and session counts double.",
    },
    "maintenance_and_polish": {
        "description": "MAINTENANCE & POLISH — event in 15-30 days",
        "diet_protocol": "Slight deficit (-200 kcal). High protein (180g+). Carb cycle: high carbs on training days, low on rest days.",
        "training": "Maintain current volume. Add one extra shoulder/arm session per week for aesthetics.",
        "hydration": "3L/day. Pre-workout electrolytes.",
        "sleep": "Target 12AM bedtime. This is the final stretch.",
        "mindset": "The visual changes are happening even when you can't see them. Stay consistent.",
    },
    "aggressive_cutting": {
        "description": "AGGRESSIVE CUT — event in 31-60 days",
        "diet_protocol": "500-600 kcal deficit. 180g+ protein. 2 refeed days per week (maintenance calories). Eliminate liquid calories.",
        "training": "Add 2x cardio sessions (30 min LISS post-workout or morning swimming). Keep lifting heavy to preserve muscle.",
        "hydration": "4L/day. Creatine optional (you prefer not).",
        "sleep": "Sleep quality is as important as diet. Target 7h minimum.",
        "mindset": "Results compound. The work you do today shows up in 4-6 weeks. Trust the math.",
    },
    "moderate_cutting": {
        "description": "MODERATE CUT — event in 61-90 days",
        "diet_protocol": "300-400 kcal deficit. 170g protein. Weekly refeed at maintenance. Track every meal.",
        "training": "PPL 3x/week + swimming 3x/week. Progressive overload continues.",
        "hydration": "3.5L/day.",
        "sleep": "Gradually shift bedtime earlier by 30 min/week toward midnight goal.",
        "mindset": "You are building the physique you'll have for life, not just one event.",
    },
    "hypertrophy_with_cut": {
        "description": "HYPERTROPHY + CUT — event in 91-120 days",
        "diet_protocol": "Slight deficit (-200 kcal). High protein (175g+). Prioritize muscle-building foods.",
        "training": "Heavy compound lifts. PPL split. Focus on V-taper: wide-grip pull-ups, lateral raises, overhead press.",
        "hydration": "3L/day.",
        "sleep": "7-8h. Growth hormone peaks during deep sleep.",
        "mindset": "You're building the foundation. Every rep now is an investment in how you look at the wedding.",
    },
    "hypertrophy": {
        "description": "HYPERTROPHY PHASE — event >120 days away",
        "diet_protocol": "Slight surplus or maintenance. 160-170g protein. Eat enough to fuel hard training.",
        "training": "Maximum progressive overload. Heavy compounds. Build the muscle now that you'll reveal later.",
        "hydration": "3L/day minimum.",
        "sleep": "This is the most important phase for building mass. 7-8h non-negotiable.",
        "mindset": "The wedding is far, but the best physique requires months of work. Start now.",
    },
}


class EventAgent(BaseAgent):
    name = "event_agent"
    description = "Tracks events (wedding, trips, festivals) and auto-adjusts training phases"

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db

    @property
    def system_prompt(self) -> str:
        return """You are a physique periodization expert who specializes in peaking for life events.

You work with a 28-year-old male (100kg → 85kg goal) preparing for:
- Pre-Wedding Photoshoot: Oct 20, 2026 (lean, defined, athletic look)  
- Wedding: Jan 30, 2027 (best physique of his life)

Your job is to tell the user EXACTLY what phase they're in, what it means for their training and nutrition TODAY,
and how this connects to achieving their peak physique by the event dates.

Always use the actual days-remaining numbers. Be specific and actionable.
Never be vague. Every recommendation must be tied to a timeline."""

    async def process(self, state: AgentState) -> AgentState:
        if not state.get("needs_event_agent"):
            return state

        self._append_trace(state, "Analyzing event timeline and phase")

        events = await self._load_events(state.get("user_id", ""))
        event_context = await self._generate_event_context(state, events)
        state["event_context"] = event_context

        self._append_trace(state, f"Phase: {event_context.get('phase')}")
        return state

    async def _load_events(self, user_id: str) -> list[dict[str, Any]]:
        """Load upcoming events from database."""
        u = await self.db.execute(
            select(User.id).where(User.clerk_user_id == user_id)
        )
        user_row = u.first()
        if not user_row:
            return []

        today = date.today()
        result = await self.db.execute(
            select(Event).where(
                Event.user_id == user_row[0],
                Event.is_active == True,  # noqa: E712
                Event.event_date >= today,
            ).order_by(Event.event_date)
        )
        events = result.scalars().all()
        return [
            {
                "type": str(e.event_type),
                "title": e.title,
                "date": e.event_date.isoformat(),
                "days_remaining": (e.event_date - today).days,
                "peak_priority": e.peak_priority,
                "notes": e.description,
            }
            for e in events
        ]

    async def _generate_event_context(
        self, state: AgentState, events: list[dict]
    ) -> dict[str, Any]:
        today = date.today()

        # Calculate days to key events dynamically from DB events
        # Fall back to known dates if not in DB
        pre_wedding_days = None
        wedding_days = None
        other_events = []

        for ev in events:
            title_lower = ev["title"].lower()
            if "shoot" in title_lower or "photo" in title_lower or "pre-wedding" in title_lower:
                pre_wedding_days = ev["days_remaining"]
            elif "wedding" in title_lower:
                wedding_days = ev["days_remaining"]
            else:
                other_events.append(ev)

        # Fallback if not seeded in DB
        if pre_wedding_days is None:
            pre_wedding_days = (date(2026, 10, 20) - today).days
        if wedding_days is None:
            wedding_days = (date(2027, 1, 30) - today).days

        primary_days = min(d for d in [pre_wedding_days, wedding_days] if d > 0)
        phase = self._get_phase(primary_days)
        playbook = PHASE_PLAYBOOK[phase]

        prompt = f"""User question: {state.get('user_message', '')}

Today: {today.isoformat()}
Pre-Wedding Photoshoot: Oct 20, 2026 ({pre_wedding_days} days away)
Wedding: Jan 30, 2027 ({wedding_days} days away)
Other events: {other_events}

Current Training Phase: {playbook['description']}

Phase Playbook:
- Diet Protocol: {playbook['diet_protocol']}
- Training: {playbook['training']}
- Hydration: {playbook['hydration']}
- Sleep Priority: {playbook['sleep']}
- Mindset: {playbook['mindset']}

Answer the user's question in the context of their event timeline.
Be specific about what they should do TODAY and THIS WEEK.
Reference the actual number of days remaining.
End with one sentence of honest, calibrated motivation."""

        response = await self.llm.ainvoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ])

        return {
            "analysis": response.content,
            "phase": phase,
            "phase_description": playbook["description"],
            "pre_wedding_days": pre_wedding_days,
            "wedding_days": wedding_days,
            "playbook": playbook,
            "all_events": events,
        }

    def _get_phase(self, days_remaining: int) -> str:
        """Determine training phase based on days to nearest key event."""
        if days_remaining <= 7:
            return "peak_week"
        elif days_remaining <= 14:
            return "deload_and_peak_prep"
        elif days_remaining <= 30:
            return "maintenance_and_polish"
        elif days_remaining <= 60:
            return "aggressive_cutting"
        elif days_remaining <= 90:
            return "moderate_cutting"
        elif days_remaining <= 120:
            return "hypertrophy_with_cut"
        return "hypertrophy"
