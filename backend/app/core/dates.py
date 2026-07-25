"""Timezone-aware date helpers."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Kolkata"


def today_in_timezone(timezone: str | None = None) -> date:
    """Return today's date in the given IANA timezone (defaults to Asia/Kolkata)."""
    tz = ZoneInfo(timezone or DEFAULT_TIMEZONE)
    return datetime.now(tz).date()
