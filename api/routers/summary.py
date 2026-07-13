"""Section 2.4 — GET /api/summary. Populates the Macro widget on the Family
Office Dashboard from the same RegimeState the /api/regime endpoint reads."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import config, regime_engine, schemas
from ..auth import get_current_user_id
from ..db import get_db
from ..util import ensure_utc, iso
from .regime import get_or_create_regime_state

router = APIRouter(prefix="/api/summary", tags=["summary"])

_STATUS_BY_REGIME = {"defensive": "warning", "neutral": "active", "offensive": "active"}
_REGIME_TREND = {"defensive": "down", "neutral": "flat", "offensive": "up"}


def _humanize_age(dt: datetime) -> str:
    delta = datetime.now(timezone.utc) - ensure_utc(dt)
    days = delta.days
    if days >= 1:
        return f"{days}d ago"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours}h ago"
    return "just now"


@router.get("", response_model=schemas.SummaryResponse)
def get_summary(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    state = get_or_create_regime_state(db, user_id)
    counts = state.signal_counts or {"bullish": 0, "neutral": 0, "bearish": 0}
    regime_label = {"offensive": "OFFENSIVE", "neutral": "NEUTRAL", "defensive": "DEFENSIVE"}[state.regime]

    headline = f"{regime_label} — {state.summary}"
    if len(headline) > 80:
        headline = headline[:77] + "..."

    since = regime_engine.posture_since(db, user_id, state.regime, state.last_evaluated)
    imbalance_msg = regime_engine.is_approaching_shift(counts, state.regime)
    action_required = state.regime == "defensive" or imbalance_msg is not None

    return schemas.SummaryResponse(
        product=config.PRODUCT_NAME,
        updated_at=iso(state.last_evaluated),
        status=_STATUS_BY_REGIME.get(state.regime, "active"),
        headline=headline,
        metrics=[
            schemas.SummaryMetric(label="Regime", value=state.regime.capitalize(), trend=_REGIME_TREND.get(state.regime)),
            schemas.SummaryMetric(label="Active Signals", value=sum(counts.values()), trend=None),
            schemas.SummaryMetric(label="Bearish Signals", value=counts.get("bearish", 0), trend=None),
            schemas.SummaryMetric(label="Last Shift", value=_humanize_age(since), trend=None),
        ],
        action_required=action_required,
        cta=schemas.SummaryCTA(label="View Signals", url="/signals") if action_required else None,
    )
