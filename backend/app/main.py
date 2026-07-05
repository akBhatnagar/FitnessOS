"""
FitnessOS FastAPI Application Entry Point.

This module creates and configures the FastAPI application instance.
All middleware, routers, and lifecycle handlers are registered here.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import engine

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.

    Startup: configure logging, verify database connectivity.
    Shutdown: close database connections gracefully.
    """
    configure_logging()
    logger.info("FitnessOS starting up", version=settings.app_version, env=settings.app_env)

    # Verify database connectivity
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("Database connection verified")
    except Exception as exc:
        logger.error("Database connection failed — check DATABASE_URL", error=str(exc))
        raise

    yield

    logger.info("FitnessOS shutting down")
    await engine.dispose()


def create_app() -> FastAPI:
    """Application factory — creates and configures the FastAPI instance."""

    app = FastAPI(
        title="FitnessOS API",
        description="Multi-Agent AI Personal Training Operating System",
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ---- CORS ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Request ID middleware ----
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # ---- Global exception handler ----
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            error=str(exc),
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An unexpected error occurred. Our team has been notified.",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    # ---- Routes ----
    app.include_router(api_router)

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        """Health check endpoint for load balancers and monitoring."""
        return {
            "status": "healthy",
            "version": settings.app_version,
            "env": settings.app_env.value,
        }

    return app


app = create_app()
