"""Swimming Agent — beginner to advanced swimming coaching."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentState, BaseAgent
from app.db.models.user import User
from app.core.logging import get_logger

logger = get_logger("agent.swimming")


# Skill levels and their progression milestones
SWIMMING_MILESTONES = {
    "absolute_beginner": {
        "description": "Not yet comfortable in water",
        "focus": "Water entry, face submersion, floating, wall kicks",
        "session_structure": "15 min max. Mostly in shallow end. No laps yet.",
        "next_milestone": "Can float independently + kick across pool with wall support",
    },
    "water_comfortable": {
        "description": "Comfortable in water, learning movement",
        "focus": "Freestyle arm motion (one arm at a time), breathing pattern (every 3 strokes)",
        "session_structure": "20-25 min. 25m kick sets with board. First full-length attempts.",
        "next_milestone": "Complete 1 full 25m length with any technique",
    },
    "learning_freestyle": {
        "description": "Can cross the pool, refining technique",
        "focus": "Bilateral breathing, body rotation, catch-and-pull mechanics",
        "session_structure": "25-30 min. 4-6x 25m with 30s rest. Focus on form over speed.",
        "next_milestone": "Complete 4x 25m continuously with breathing every 3 strokes",
    },
    "building_endurance": {
        "description": "Has the stroke, building stamina",
        "focus": "Continuous swimming, pacing, increasing distance per set",
        "session_structure": "30-35 min. 2-4x 50m. Introduce flip turns.",
        "next_milestone": "Complete 200m (8 lengths) without stopping",
    },
    "intermediate": {
        "description": "Can swim continuously for 200m+",
        "focus": "Speed, turns, introducing backstroke, interval training",
        "session_structure": "35-40 min. 400-600m total volume. Mix drills and laps.",
        "next_milestone": "Complete 500m in under 12 minutes",
    },
    "fat_loss_swimmer": {
        "description": "Swimming for fitness and fat loss",
        "focus": "HIIT intervals (swim fast + rest), high-intensity to maximize calorie burn",
        "session_structure": "40 min. 6-8x 50m at 80% effort, 20s rest. Or 4x 100m.",
        "next_milestone": "Sustain 1000m sessions at moderate intensity",
    },
}


class SwimmingAgent(BaseAgent):
    name = "swimming_agent"
    description = "Beginner swimming lessons, technique progression, stroke and endurance coaching"

    def __init__(self, db: AsyncSession) -> None:
        super().__init__()
        self.db = db

    @property
    def system_prompt(self) -> str:
        return """You are a professional adult swimming coach specializing in beginner to intermediate progression.

Your approach:
1. WATER CONFIDENCE first — never rush a nervous beginner
2. BREATHING RHYTHM is the #1 skill — master it before distance
3. TECHNIQUE over distance — 25m with good form beats 200m with bad form
4. FREQUENCY over duration — 3x/week short sessions beat 1x/week long session
5. CELEBRATE small wins — first full length is a massive achievement

You are coaching a 28-year-old male (100kg, 6'1") who:
- Swims at 8:00 AM (before office)
- Has access to a pool daily
- Goal: Build to swimming for fat loss (cardio + calories burned)
- Also: Build water confidence and athletic identity

Always be encouraging, specific, and safety-conscious.
Always suggest what to practice TODAY in the session."""

    async def process(self, state: AgentState) -> AgentState:
        if not state.get("needs_swimming_agent"):
            return state

        self._append_trace(state, "Loading swimming history and generating coaching advice")

        user_id = state.get("user_id", "")
        sessions = await self._get_recent_sessions(user_id)
        skill_level = self._assess_skill_level(sessions)
        context = await self._generate_swimming_context(state, sessions, skill_level)
        state["swimming_context"] = context

        self._append_trace(state, f"Swimming skill assessed: {skill_level}")
        return state

    async def _get_recent_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """Load recent swimming sessions from the database."""
        u = await self.db.execute(
            select(User.id).where(User.clerk_user_id == user_id)
        )
        user_row = u.first()
        if not user_row:
            return []

        # Query swimming_sessions table directly (model may not be imported)
        result = await self.db.execute(text("""
            SELECT ss.session_date, ss.duration_minutes, ss.total_distance_m,
                   ss.technique_focus, ss.confidence_level, ss.notes,
                   ss.completed_laps, ss.session_rating
            FROM swimming_sessions ss
            JOIN users u ON ss.user_id = u.id
            WHERE u.clerk_user_id = :user_id
              AND ss.session_date >= :since
            ORDER BY ss.session_date DESC
            LIMIT 10
        """), {
            "user_id": user_id,
            "since": (date.today() - timedelta(days=30)).isoformat(),
        })

        sessions = result.fetchall()
        return [
            {
                "date": str(row.session_date),
                "duration_min": row.duration_minutes,
                "distance_m": row.total_distance_m,
                "focus": row.technique_focus,
                "confidence": row.confidence_level,
                "notes": row.notes,
                "laps": row.completed_laps,
                "rating": row.session_rating,
            }
            for row in sessions
        ]

    def _assess_skill_level(self, sessions: list[dict]) -> str:
        """Infer skill level from session history."""
        if not sessions:
            return "absolute_beginner"

        # Latest average distance and laps
        recent = sessions[:3]
        avg_distance = sum(s.get("distance_m") or 0 for s in recent) / len(recent)
        avg_laps = sum(s.get("laps") or 0 for s in recent) / len(recent)

        if avg_distance >= 500 or avg_laps >= 20:
            return "fat_loss_swimmer"
        elif avg_distance >= 200 or avg_laps >= 8:
            return "intermediate"
        elif avg_distance >= 100 or avg_laps >= 4:
            return "building_endurance"
        elif avg_distance >= 25 or avg_laps >= 1:
            return "learning_freestyle"
        elif len(sessions) >= 3:
            return "water_comfortable"
        return "absolute_beginner"

    async def _generate_swimming_context(
        self,
        state: AgentState,
        sessions: list[dict],
        skill_level: str,
    ) -> dict[str, Any]:
        milestone = SWIMMING_MILESTONES[skill_level]
        total_sessions = len(sessions)
        last_session = sessions[0] if sessions else None

        prompt = f"""Swimming question: {state.get('user_message', '')}

USER SWIMMING PROFILE:
- Total sessions logged: {total_sessions}
- Current skill level: {skill_level}
- Level description: {milestone['description']}

LAST SESSION:
{json.dumps(last_session, indent=2) if last_session else "No previous sessions recorded — first time!"}

CURRENT FOCUS: {milestone['focus']}
TYPICAL SESSION STRUCTURE: {milestone['session_structure']}
NEXT MILESTONE TO HIT: {milestone['next_milestone']}

RECENT SESSIONS (last 3):
{json.dumps(sessions[:3], indent=2) if sessions else "None yet"}

Answer the user's swimming question with:
1. Assessment of where they are right now (specific, based on their history)
2. TODAY'S SESSION PLAN — exact drills, distances, rest times (be very specific)
3. One technique tip to focus on this session
4. What to look for to know they're ready to progress
5. A confidence-building note (swimming is hard — acknowledge that)

If it's their first time: extra warmth, zero pressure, start with step 1 (entering the water comfortably)."""

        response = await self.llm.ainvoke([
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ])

        return {
            "analysis": response.content,
            "skill_level": skill_level,
            "milestone": milestone,
            "total_sessions": total_sessions,
            "last_session": last_session,
            "sessions_history": sessions,
        }
