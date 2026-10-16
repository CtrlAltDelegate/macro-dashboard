"""Section 3.3 — /api/indicators CRUD."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models_db as m, schemas
from ..auth import get_current_user_id
from ..db import get_db
from ..util import iso

router = APIRouter(prefix="/api/indicators", tags=["indicators"])


def _to_out(i: m.MacroIndicator) -> schemas.IndicatorOut:
    return schemas.IndicatorOut(
        id=i.id, user_id=i.user_id, name=i.name, value=i.value,
        prior_value=i.prior_value, direction=i.direction,
        as_of=iso(i.as_of), notes=i.notes,
    )


@router.get("", response_model=schemas.IndicatorsListResponse)
def list_indicators(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    rows = db.query(m.MacroIndicator).filter_by(user_id=user_id).order_by(m.MacroIndicator.created_at.desc()).all()
    return schemas.IndicatorsListResponse(indicators=[_to_out(i) for i in rows])


@router.post("", response_model=schemas.IndicatorOut, status_code=201)
def create_indicator(
    body: schemas.IndicatorCreate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    indicator = m.MacroIndicator(
        user_id=user_id, name=body.name, value=body.value,
        prior_value=body.prior_value, direction=body.direction,
        as_of=body.as_of or datetime.now(timezone.utc), notes=body.notes,
    )
    db.add(indicator)
    db.commit()
    db.refresh(indicator)
    return _to_out(indicator)


@router.put("/{indicator_id}", response_model=schemas.IndicatorOut)
def update_indicator(
    indicator_id: str,
    body: schemas.IndicatorUpdate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    indicator = db.query(m.MacroIndicator).filter_by(id=indicator_id, user_id=user_id).first()
    if indicator is None:
        raise HTTPException(status_code=404, detail="Indicator not found")
    for field in ("name", "value", "prior_value", "direction", "as_of", "notes"):
        val = getattr(body, field)
        if val is not None:
            setattr(indicator, field, val)
    db.commit()
    db.refresh(indicator)
    return _to_out(indicator)


@router.delete("/{indicator_id}", status_code=204)
def delete_indicator(
    indicator_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    indicator = db.query(m.MacroIndicator).filter_by(id=indicator_id, user_id=user_id).first()
    if indicator is None:
        raise HTTPException(status_code=404, detail="Indicator not found")
    db.delete(indicator)
    db.commit()
    return None
