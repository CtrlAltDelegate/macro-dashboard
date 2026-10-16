"""Alert generation — see KFH Integration Spec Section 4. Regime-shift alerts
are triggered from api/routers/regime.py right after an evaluation writes a
new RegimeState; signal-update alerts from api/routers/signals.py."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import models_db as m

REGIME_LABELS = {"offensive": "Offensive", "neutral": "Neutral", "defensive": "Defensive"}


def _recent_duplicate_exists(db: Session, user_id: str, title: str) -> bool:
    """Basic same-day dedupe so repeated /api/regime/evaluate calls (or an
    imbalance that persists across polling intervals) don't spam identical
    alerts."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    return (
        db.query(m.Alert)
        .filter(
            m.Alert.user_id == user_id,
            m.Alert.title == title,
            m.Alert.dismissed.is_(False),
            m.Alert.created_at >= cutoff,
        )
        .first()
        is not None
    )


def create_alert(
    db: Session,
    user_id: str,
    severity: str,
    title: str,
    body: str | None = None,
    action_url: str | None = None,
    dedupe: bool = True,
) -> m.Alert | None:
    if dedupe and _recent_duplicate_exists(db, user_id, title):
        return None
    alert = m.Alert(
        user_id=user_id, product="macro-dashboard", severity=severity,
        title=title, body=body, action_url=action_url,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def alert_for_regime_shift(db: Session, user_id: str, from_regime: str | None, to_regime: str) -> m.Alert | None:
    """Section 4: critical only for Offensive<->Defensive; warning for any
    other actual shift (e.g. involving Neutral)."""
    if from_regime is None or from_regime == to_regime:
        return None
    from_label, to_label = REGIME_LABELS.get(from_regime, from_regime), REGIME_LABELS.get(to_regime, to_regime)
    title = f"REGIME SHIFT: {from_label} → {to_label}"
    if {from_regime, to_regime} == {"offensive", "defensive"}:
        severity = "critical"
        body = "review all positions" if to_regime == "defensive" else "redeployment opportunity"
    else:
        severity = "warning"
        body = f"Regime shift: {from_label} → {to_label}"
    return create_alert(db, user_id, severity, title, body, action_url="/regime", dedupe=False)


def alert_for_imbalance(db: Session, user_id: str, message: str | None) -> m.Alert | None:
    if not message:
        return None
    return create_alert(db, user_id, "warning", message, action_url="/signals")


def alert_for_signal_update(db: Session, user_id: str, signal_name: str, stance: str) -> m.Alert | None:
    title = f"{signal_name} signal updated: {stance.capitalize()}"
    return create_alert(db, user_id, "info", title, action_url="/signals")


def alert_for_unchanged_evaluation(db: Session, user_id: str, regime: str) -> m.Alert | None:
    label = REGIME_LABELS.get(regime, regime)
    title = f"Regime re-evaluated — {label} posture confirmed"
    return create_alert(db, user_id, "info", title, action_url="/regime")
