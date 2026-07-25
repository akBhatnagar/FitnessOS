"""
Chat API — the primary interface for conversing with FitnessOS.

All AI coaching interactions flow through this endpoint.
Supports both streaming (SSE progress) and non-streaming responses.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import run_agent_pipeline, stream_agent_pipeline
from app.core.security import TokenPayload, get_current_user
from app.db.session import AsyncSessionLocal, get_db
from app.core.logging import get_logger, bind_request_context

logger = get_logger("api.chat")
router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = Field(None, description="Continue an existing conversation")
    stream: bool = Field(False, description="Stream progress + final response via SSE")


class ChatResponse(BaseModel):
    response: str
    session_id: str
    agent_trace: list[str] = []
    follow_up_suggestions: list[str] = []
    confidence_score: float | None = None
    request_id: str


def _response_from_state(final_state: dict[str, Any], session_id: str, request_id: str) -> ChatResponse:
    return ChatResponse(
        response=final_state.get("final_response", ""),
        session_id=session_id,
        agent_trace=final_state.get("agent_trace", []),
        follow_up_suggestions=final_state.get("follow_up_suggestions", []),
        confidence_score=final_state.get("confidence_score"),
        request_id=request_id,
    )


def _sse(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


@router.post("/message")
async def send_message(
    request: ChatRequest,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message to FitnessOS and receive a personalized coaching response.

    When stream=true, returns Server-Sent Events with status updates while
    the multi-agent pipeline runs, then a final done event with the response.
    """
    session_id = request.session_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    bind_request_context(
        request_id=request_id,
        user_id=current_user.sub,
        path="/api/v1/chat/message",
    )

    logger.info("Chat request received", session_id=session_id, stream=request.stream)

    if request.stream:
        # Own session for the stream lifetime — request-scoped Depends(db)
        # can close before the SSE generator finishes.
        return StreamingResponse(
            _stream_chat(
                message=request.message,
                user_id=current_user.sub,
                session_id=session_id,
                request_id=request_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    final_state = await run_agent_pipeline(
        user_message=request.message,
        user_id=current_user.sub,
        session_id=session_id,
        db=db,
        request_id=request_id,
    )

    if final_state.get("error") and not final_state.get("final_response"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate a coaching response. Please try again.",
        )

    return _response_from_state(final_state, session_id, request_id)


async def _stream_chat(
    message: str,
    user_id: str,
    session_id: str,
    request_id: str,
) -> AsyncGenerator[str, None]:
    yield _sse(
        {
            "type": "status",
            "node": "start",
            "message": "Working on it…",
        }
    )

    async with AsyncSessionLocal() as db:
        try:
            async for event in stream_agent_pipeline(
                user_message=message,
                user_id=user_id,
                session_id=session_id,
                db=db,
                request_id=request_id,
            ):
                event_type = event.get("type")
                if event_type == "status":
                    yield _sse(
                        {
                            "type": "status",
                            "node": event.get("node"),
                            "message": event.get("message", "Working on it…"),
                        }
                    )
                elif event_type == "heartbeat":
                    yield _sse({"type": "heartbeat"})
                elif event_type == "done":
                    state = event.get("state") or {}
                    payload = _response_from_state(state, session_id, request_id)
                    await db.commit()
                    yield _sse({"type": "done", **payload.model_dump()})
                elif event_type == "error":
                    state = event.get("state") or {}
                    payload = _response_from_state(state, session_id, request_id)
                    await db.rollback()
                    yield _sse(
                        {
                            "type": "error",
                            "message": payload.response
                            or "I encountered an issue. Please try again.",
                            **payload.model_dump(),
                        }
                    )
        except Exception:
            await db.rollback()
            raise


class ConversationHistoryResponse(BaseModel):
    messages: list[dict]
    session_id: str
    total_count: int


@router.get("/history/{session_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> ConversationHistoryResponse:
    """Retrieve conversation history for a session."""
    from sqlalchemy import select
    from app.db.models.memory import ConversationMessage
    from app.db.models.user import User

    result = await db.execute(
        select(ConversationMessage)
        .join(User, ConversationMessage.user_id == User.id)
        .where(
            User.clerk_user_id == current_user.sub,
            ConversationMessage.session_id == session_id,
        )
        .order_by(ConversationMessage.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    messages = result.scalars().all()

    return ConversationHistoryResponse(
        messages=[
            {
                "id": str(msg.id),
                "role": msg.role,
                "content": msg.content,
                "agent_name": msg.agent_name,
                "created_at": msg.created_at.isoformat(),
            }
            for msg in messages
        ],
        session_id=session_id,
        total_count=len(messages),
    )
