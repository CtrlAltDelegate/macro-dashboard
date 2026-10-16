"""Small shared helpers for the routers."""
from __future__ import annotations

from datetime import datetime, timezone


def ensure_utc(dt: datetime | None) -> datetime | None:
    """SQLite (the local dev DB fallback) doesn't persist tzinfo even on a
    DateTime(timezone=True) column, so values read back are naive. Postgres
    returns tz-aware values already, making this a no-op there. Always treat
    a naive value as UTC (everything we write is datetime.now(timezone.utc))."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def iso(dt: datetime | None) -> str | None:
    dt = ensure_utc(dt)
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")
