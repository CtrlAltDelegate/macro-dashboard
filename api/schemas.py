"""Pydantic request/response schemas — field names, types, and enums mirror
the KFH Integration Spec (Sections 2-3) exactly."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Stance = Literal["bullish", "neutral", "bearish"]
Regime = Literal["offensive", "neutral", "defensive"]
Confidence = Literal["high", "medium", "low"]
Severity = Literal["critical", "warning", "info"]
Trend = Literal["up", "down", "flat"]
Direction = Literal["up", "down", "flat"]
Category = Literal["rates", "credit", "inflation", "employment", "growth", "liquidity", "sentiment"]


# ----- 2.3 Health -----
class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    product: str
    version: str
    timestamp: str


# ----- 2.4 Summary -----
class SummaryMetric(BaseModel):
    label: str
    value: str | int | float
    trend: Optional[Trend] = None


class SummaryCTA(BaseModel):
    label: str
    url: str


class SummaryResponse(BaseModel):
    product: str
    updated_at: str
    status: Literal["active", "idle", "warning", "error"]
    headline: str = Field(max_length=80)
    metrics: list[SummaryMetric]
    action_required: bool
    cta: Optional[SummaryCTA] = None


# ----- 2.5 Alerts -----
class AlertOut(BaseModel):
    id: str
    product: str
    user_id: str
    severity: Severity
    title: str
    body: Optional[str] = None
    created_at: str
    expires_at: Optional[str] = None
    action_url: Optional[str] = None
    dismissed: bool

    model_config = {"from_attributes": True}


class AlertsListResponse(BaseModel):
    alerts: list[AlertOut]
    total: int
    unread: int


class AlertPatch(BaseModel):
    dismissed: bool


# ----- 3.1 Regime -----
class SignalCounts(BaseModel):
    bullish: int
    neutral: int
    bearish: int


class RegimeResponse(BaseModel):
    regime: Regime
    confidence: Confidence
    posture_since: str
    previous_regime: Optional[Regime] = None
    last_evaluated: str
    summary: str
    signal_counts: SignalCounts


# ----- 3.4 Regime history -----
class RegimeHistoryEntry(BaseModel):
    id: str
    from_regime: Optional[Regime] = None
    to_regime: Regime
    shifted_at: str
    rationale: Optional[str] = None
    signal_snapshot: Optional[dict] = None


class RegimeHistoryResponse(BaseModel):
    history: list[RegimeHistoryEntry]


# ----- 3.2 Signals -----
class SignalOut(BaseModel):
    id: str
    user_id: str
    name: str
    category: Optional[Category] = None
    current_value: Optional[str] = None
    stance: Stance
    notes: Optional[str] = None
    last_updated: str
    source: Optional[str] = None

    model_config = {"from_attributes": True}


class SignalsListResponse(BaseModel):
    signals: list[SignalOut]
    count: int


class SignalCreate(BaseModel):
    name: str
    category: Optional[Category] = None
    current_value: Optional[str] = None
    stance: Stance = "neutral"
    notes: Optional[str] = None
    source: Optional[str] = None


class SignalUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[Category] = None
    current_value: Optional[str] = None
    stance: Optional[Stance] = None
    notes: Optional[str] = None
    source: Optional[str] = None
    active: Optional[bool] = None


# ----- 3.3 Indicators -----
class IndicatorOut(BaseModel):
    id: str
    user_id: str
    name: str
    value: Optional[str] = None
    prior_value: Optional[str] = None
    direction: Optional[Direction] = None
    as_of: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class IndicatorsListResponse(BaseModel):
    indicators: list[IndicatorOut]


class IndicatorCreate(BaseModel):
    name: str
    value: Optional[str] = None
    prior_value: Optional[str] = None
    direction: Optional[Direction] = None
    as_of: Optional[datetime] = None
    notes: Optional[str] = None


class IndicatorUpdate(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    prior_value: Optional[str] = None
    direction: Optional[Direction] = None
    as_of: Optional[datetime] = None
    notes: Optional[str] = None
