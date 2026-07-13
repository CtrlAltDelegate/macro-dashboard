"""Section 2.5 — /api/alerts, PATCH /api/alerts/:id."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models_db as m, schemas
from ..auth import get_current_user_id
from ..db import get_db
from ..util import iso

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _to_out(a: m.Alert) -> schemas.AlertOut:
    return schemas.AlertOut(
        id=a.id, product=a.product, user_id=a.user_id, severity=a.severity,
        title=a.title, body=a.body, created_at=iso(a.created_at),
        expires_at=iso(a.expires_at), action_url=a.action_url, dismissed=a.dismissed,
    )


@router.get("", response_model=schemas.AlertsListResponse)
def list_alerts(
    limit: int = Query(50, ge=1, le=200),
    severity: str | None = Query(None, description="Comma-separated: critical,warning,info"),
    dismissed: bool | None = Query(None),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    q = db.query(m.Alert).filter_by(user_id=user_id)
    if severity:
        sevs = [s.strip() for s in severity.split(",") if s.strip()]
        if sevs:
            q = q.filter(m.Alert.severity.in_(sevs))
    if dismissed is not None:
        q = q.filter(m.Alert.dismissed == dismissed)
    total = q.count()
    unread = db.query(m.Alert).filter_by(user_id=user_id, dismissed=False).count()
    rows = q.order_by(m.Alert.created_at.desc()).limit(limit).all()
    return schemas.AlertsListResponse(alerts=[_to_out(a) for a in rows], total=total, unread=unread)


@router.patch("/{alert_id}", response_model=schemas.AlertOut)
def patch_alert(
    alert_id: str,
    body: schemas.AlertPatch,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    alert = db.query(m.Alert).filter_by(id=alert_id, user_id=user_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.dismissed = body.dismissed
    db.commit()
    db.refresh(alert)
    return _to_out(alert)
