"""Section 3.2 — /api/signals CRUD, with lazy auto-seeding from the existing
FRED-driven models on first access for a user (see api/regime_engine.py)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import alerts_engine, models_db as m, regime_engine, schemas
from ..auth import get_current_user_id
from ..db import get_db
from ..util import iso

router = APIRouter(prefix="/api/signals", tags=["signals"])


def _to_out(s: m.MacroSignal) -> schemas.SignalOut:
    return schemas.SignalOut(
        id=s.id, user_id=s.user_id, name=s.name, category=s.category,
        current_value=s.current_value, stance=s.stance, notes=s.notes,
        last_updated=iso(s.last_updated), source=s.source,
    )


@router.get("", response_model=schemas.SignalsListResponse)
def list_signals(
    stance: str | None = Query(None),
    category: str | None = Query(None, description="Comma-separated categories"),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    if db.query(m.MacroSignal).filter_by(user_id=user_id, active=True).count() == 0:
        regime_engine.sync_auto_signals(db, user_id)

    q = db.query(m.MacroSignal).filter_by(user_id=user_id, active=True)
    if stance:
        q = q.filter(m.MacroSignal.stance == stance)
    if category:
        cats = [c.strip() for c in category.split(",") if c.strip()]
        if cats:
            q = q.filter(m.MacroSignal.category.in_(cats))
    rows = q.order_by(m.MacroSignal.last_updated.desc()).all()
    return schemas.SignalsListResponse(signals=[_to_out(s) for s in rows], count=len(rows))


@router.post("", response_model=schemas.SignalOut, status_code=201)
def create_signal(
    body: schemas.SignalCreate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    signal = m.MacroSignal(
        user_id=user_id, name=body.name, category=body.category,
        current_value=body.current_value, stance=body.stance,
        notes=body.notes, source=body.source or "manual", active=True,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    alerts_engine.alert_for_signal_update(db, user_id, signal.name, signal.stance)
    return _to_out(signal)


@router.put("/{signal_id}", response_model=schemas.SignalOut)
def update_signal(
    signal_id: str,
    body: schemas.SignalUpdate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    signal = db.query(m.MacroSignal).filter_by(id=signal_id, user_id=user_id).first()
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    stance_changed = body.stance is not None and body.stance != signal.stance
    for field in ("name", "category", "current_value", "stance", "notes", "source", "active"):
        val = getattr(body, field)
        if val is not None:
            setattr(signal, field, val)
    signal.last_updated = datetime.now(timezone.utc)
    db.commit()
    db.refresh(signal)
    if stance_changed:
        alerts_engine.alert_for_signal_update(db, user_id, signal.name, signal.stance)
    return _to_out(signal)


@router.delete("/{signal_id}", status_code=204)
def delete_signal(
    signal_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    signal = db.query(m.MacroSignal).filter_by(id=signal_id, user_id=user_id).first()
    if signal is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    db.delete(signal)
    db.commit()
    return None
