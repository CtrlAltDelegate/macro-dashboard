"""
SQLAlchemy ORM models — matches KFH Integration Spec Section 5 exactly.

UUID columns are stored as String(36) rather than a Postgres-native UUID type
so the same models work against local SQLite (dev) and Supabase/Postgres
(prod) without branching code. Values are still real UUID4 strings.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, String, Text, func
from sqlalchemy.types import JSON

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MacroSignal(Base):
    __tablename__ = "macro_signals"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    name = Column(Text, nullable=False)
    category = Column(Text)  # rates | credit | inflation | employment | growth | liquidity | sentiment
    current_value = Column(Text)
    stance = Column(Text)  # bullish | neutral | bearish
    notes = Column(Text)
    source = Column(Text)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    active = Column(Boolean, default=True, nullable=False)


class MacroIndicator(Base):
    __tablename__ = "macro_indicators"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    name = Column(Text, nullable=False)
    value = Column(Text)
    prior_value = Column(Text)
    direction = Column(Text)  # up | down | flat
    as_of = Column(DateTime(timezone=True))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RegimeState(Base):
    """One active row per user_id. Re-evaluation updates in place; the prior
    state is written to RegimeHistory first."""
    __tablename__ = "regime_state"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), nullable=False, unique=True, index=True)
    regime = Column(Text, nullable=False)  # offensive | neutral | defensive
    confidence = Column(Text)  # high | medium | low
    summary = Column(Text)
    signal_counts = Column(JSON)  # {"bullish": n, "neutral": n, "bearish": n}
    last_evaluated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RegimeHistory(Base):
    __tablename__ = "regime_history"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    from_regime = Column(Text)
    to_regime = Column(Text, nullable=False)
    shifted_at = Column(DateTime(timezone=True), server_default=func.now())
    rationale = Column(Text)
    signal_snapshot = Column(JSON)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), nullable=False, index=True)
    product = Column(Text, default="macro-dashboard", nullable=False)
    severity = Column(Text, nullable=False)  # critical | warning | info
    title = Column(Text, nullable=False)
    body = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    action_url = Column(Text, nullable=True)
    dismissed = Column(Boolean, default=False, nullable=False)
