"""Rate limiting middleware using Redis."""

from __future__ import annotations

import time

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("middleware.rate_limit")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter using Redis.

    Limits:
    - General: 60 requests/minute per user
    - Chat endpoint: 20 requests/minute per user
    """

    def __init__(self, app, redis_url: str | None = None) -> None:
        super().__init__(app)
        self._redis: aioredis.Redis | None = None
        self.redis_url = redis_url or settings.redis_url

    async def _get_redis(self) -> aioredis.Redis:
        if not self._redis:
            self._redis = await aioredis.from_url(self.redis_url)
        return self._redis

    async def dispatch(self, request: Request, call_next):
        # Extract user identifier
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            # Fall back to IP for unauthenticated requests
            user_id = request.client.host if request.client else "anonymous"

        # Determine limit based on path
        is_chat = "/chat/" in request.url.path
        limit = settings.rate_limit_chat_per_minute if is_chat else settings.rate_limit_requests_per_minute
        window = 60  # 1 minute

        try:
            redis = await self._get_redis()
            key = f"rate_limit:{user_id}:{request.url.path}"
            now = time.time()
            window_start = now - window

            # Sliding window using sorted set
            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window)
            results = await pipe.execute()

            request_count = results[2]

            if request_count > limit:
                logger.warning("Rate limit exceeded", user_id=user_id, path=request.url.path)
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Rate limit exceeded. Please slow down."},
                    headers={"Retry-After": str(window)},
                )

        except Exception as exc:
            # Never fail a request due to rate limiting issues
            logger.error("Rate limit check failed", error=str(exc))

        return await call_next(request)
