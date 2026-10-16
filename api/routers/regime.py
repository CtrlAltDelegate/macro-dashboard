"""Section 3.1, 3.4 — /api/regime, /api/regime/history, /api/regime/evaluate."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import alerts_engine, models_db as m, regime_engine, schemas
from ..auth import get_current_user_id
from ..db import get_db
from ..util import iso

router = APIRouter(prefix="/api/regime", tags=["regime"])


def _evaluate_and_persist(db: Session, user_id: str) -> m.RegimeState:
    """Recomputes regime from currently-stored signals (no external fetch —
    matches the spec's 'Body: {} — uses stored signal states' contract),
    upserts RegimeState, and on an actual change writes RegimeHistory and
    fires the Section 4 alerts."""
    counts = regime_engine.tally_signal_counts(db, user_id)
    regime, confidence = regime_engine.derive_regime_from_counts(counts)
    summary = regime_engine.build_summary(regime, counts)

    existing = db.query(m.RegimeState).filter_by(user_id=user_id).first()
    previous_regime = existing.regime if existing else None
    now = datetime.now(timezone.utc)

    if existing:
        existing.regime = regime
        existing.confidence = confidence
        existing.summary = summary
        existing.signal_counts = counts
        existing.last_evaluated = now
        state = existing
    else:
        state = m.RegimeState(
            user_id=user_id, regime=regime, confidence=confidence,
            summary=summary, signal_counts=counts, last_evaluated=now,
        )
        db.add(state)
    db.commit()
    db.refresh(state)

    changed = previous_regime is not None and previous_regime != regime
    if changed:
        db.add(m.RegimeHistory(
            user_id=user_id, from_regime=previous_regime, to_regime=regime,
            rationale=summary, signal_snapshot=counts,
        ))
        db.commit()
        alerts_engine.alert_for_regime_shift(db, user_id, previous_regime, regime)
    elif previous_regime is not None:
        alerts_engine.alert_for_unchanged_evaluation(db, user_id, regime)

    imbalance_msg = regime_engine.is_approaching_shift(counts, regime)
    alerts_engine.alert_for_imbalance(db, user_id, imbalance_msg)
    return state


def get_or_create_regime_state(db: Session, user_id: str) -> m.RegimeState:
    state = db.query(m.RegimeState).filter_by(user_id=user_id).first()
    if state is not None:
        return state
    if db.query(m.MacroSignal).filter_by(user_id=user_id, active=True).count() == 0:
        regime_engine.sync_auto_signals(db, user_id)
    return _evaluate_and_persist(db, user_id)


def _to_response(db: Session, user_id: str, state: m.RegimeState) -> schemas.RegimeResponse:
    return schemas.RegimeResponse(
        regime=state.regime,
        confidence=state.confidence,
        posture_since=iso(regime_engine.posture_since(db, user_id, state.regime, state.last_evaluated)),
        previous_regime=regime_engine.previous_regime(db, user_id, state.regime),
        last_evaluated=iso(state.last_evaluated),
        summary=state.summary,
        signal_counts=state.signal_counts,
    )


@router.get("", response_model=schemas.RegimeResponse)
def get_regime(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    state = get_or_create_regime_state(db, user_id)
    return _to_response(db, user_id, state)


@router.get("/history", response_model=schemas.RegimeHistoryResponse)
def get_regime_history(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    rows = (
        db.query(m.RegimeHistory)
        .filter_by(user_id=user_id)
        .order_by(m.RegimeHistory.shifted_at.desc())
        .all()
    )
    return schemas.RegimeHistoryResponse(history=[
        schemas.RegimeHistoryEntry(
            id=r.id, from_regime=r.from_regime, to_regime=r.to_regime,
            shifted_at=iso(r.shifted_at), rationale=r.rationale,
            signal_snapshot=r.signal_snapshot,
        )
        for r in rows
    ])


@router.post("/evaluate", response_model=schemas.RegimeResponse)
def evaluate_regime(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    state = _evaluate_and_persist(db, user_id)
    return _to_response(db, user_id, state)
