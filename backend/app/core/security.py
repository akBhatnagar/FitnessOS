"""
Security utilities: JWT verification (Clerk), API key validation, and RBAC.

This module is model-agnostic with respect to auth providers.
Switching from Clerk to another provider requires changing only this file.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)

# Cached JWKS — refreshed automatically on key rotation
_jwks_cache: dict[str, Any] = {}
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 3600  # 1 hour


async def _get_jwks() -> dict[str, Any]:
    """Fetch JWKS from Clerk. Cached for one hour."""
    global _jwks_cache, _jwks_fetched_at

    if time.monotonic() - _jwks_fetched_at < _JWKS_TTL and _jwks_cache:
        return _jwks_cache

    jwks_url = f"{settings.clerk_jwt_issuer}/.well-known/jwks.json"
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url, timeout=10.0)
        response.raise_for_status()

    _jwks_cache = response.json()
    _jwks_fetched_at = time.monotonic()
    return _jwks_cache


class TokenPayload(BaseModel):
    sub: str  # Clerk user ID
    email: str | None = None
    roles: list[str] = []
    iat: int | None = None
    exp: int | None = None


async def verify_clerk_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> TokenPayload:
    """
    Verify a Clerk-issued JWT and return the decoded payload.

    In development mode (APP_ENV=development), accepts a special dev token
    so the API can be tested without a real Clerk account.
    Raises HTTP 401 for any verification failure in production.
    """
    # ---- Development bypass ----
    # In dev mode, accept "dev-token" header value to skip Clerk verification.
    # This NEVER runs in production (APP_ENV != development).
    if settings.is_development:
        if credentials is None or credentials.credentials in ("dev-token", "devtoken", "local"):
            return TokenPayload(sub="dev-user-001", email="dev@fitnessos.local", roles=["user"])

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        jwks = await _get_jwks()
        # jose handles key selection via the "kid" header
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            issuer=settings.clerk_jwt_issuer,
            options={"verify_audience": False},
        )
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise credentials_exception

        return TokenPayload(
            sub=user_id,
            email=payload.get("email"),
            roles=payload.get("roles", []),
            iat=payload.get("iat"),
            exp=payload.get("exp"),
        )

    except JWTError as exc:
        logger.warning("JWT verification failed", error=str(exc))
        raise credentials_exception from exc
    except Exception as exc:
        logger.error("Unexpected error during token verification", error=str(exc))
        raise credentials_exception from exc


async def get_current_user(
    token: TokenPayload = Depends(verify_clerk_token),
) -> TokenPayload:
    """FastAPI dependency: returns the current authenticated user's token payload."""
    return token


def require_role(required_role: str):
    """
    FastAPI dependency factory that enforces role-based access control.

    Usage:
        @router.get("/admin", dependencies=[Depends(require_role("admin"))])
    """

    async def check_role(
        token: TokenPayload = Depends(get_current_user),
    ) -> TokenPayload:
        if required_role not in token.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' is required.",
            )
        return token

    return check_role
