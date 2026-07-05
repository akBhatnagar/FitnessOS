"""
Structured logging configuration using structlog.

All logs are emitted as JSON in production for ingestion by log aggregators
(Datadog, Loki, CloudWatch, etc.). Console format is used in development.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from app.core.config import settings


def add_app_context(
    logger: logging.Logger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Inject application-level context into every log entry."""
    event_dict["app"] = settings.app_name
    event_dict["version"] = settings.app_version
    event_dict["env"] = settings.app_env.value
    return event_dict


def configure_logging() -> None:
    """Configure structlog for the application. Called once at startup."""
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_app_context,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Silence noisy third-party loggers
    for noisy_logger in ["httpx", "httpcore", "uvicorn.access"]:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a named structlog logger. Use at module level."""
    return structlog.get_logger(name)


def bind_request_context(
    request_id: str,
    user_id: str | None = None,
    path: str | None = None,
) -> None:
    """Bind per-request context variables into the current async context."""
    ctx: dict[str, Any] = {"request_id": request_id}
    if user_id:
        ctx["user_id"] = user_id
    if path:
        ctx["path"] = path
    structlog.contextvars.bind_contextvars(**ctx)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()
