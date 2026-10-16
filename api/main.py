"""
KFH integration API — FastAPI service, run separately from the Streamlit app:

    uvicorn api.main:app --reload --port 8000

See KFH Integration Spec — Macro Dashboard for the full contract.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .db import init_db
from .routers import alerts, health, indicators, regime, signals, summary

logger = logging.getLogger(__name__)

app = FastAPI(title="Macro Dashboard API", version=config.VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    # Non-fatal: if the DB is unreachable at boot, the app should still come
    # up so GET /health can report 503 rather than the process failing to start.
    try:
        init_db()
    except Exception:
        logger.exception("init_db() failed at startup — /health will report 503 until the DB is reachable")


app.include_router(health.router)
app.include_router(summary.router)
app.include_router(alerts.router)
app.include_router(regime.router)
app.include_router(signals.router)
app.include_router(indicators.router)
