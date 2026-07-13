"""Section 2.3 — GET /health. No auth required."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Response

from .. import config
from ..db import db_is_reachable

router = APIRouter(tags=["health"])


@router.get("/health")
def health(response: Response):
    ok = db_is_reachable()
    if not ok:
        response.status_code = 503
    return {
        "status": "ok" if ok else "error",
        "product": config.PRODUCT_NAME,
        "version": config.VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
