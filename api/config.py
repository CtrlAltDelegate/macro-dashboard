"""
Config for the KFH integration API (FastAPI service, separate process from the
Streamlit app). See KFH Integration Spec — Macro Dashboard.

All values are environment-driven so the JWT issuer and database can be swapped
later (e.g. Clerk -> Supabase Auth, SQLite -> Supabase Postgres) without code
changes, per the spec's own "swap issuer later" intent.
"""
import os

PRODUCT_NAME = "macro-dashboard"
VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Database — defaults to a local SQLite file for zero-setup dev; point
# DATABASE_URL at a Supabase (or any) Postgres connection string for production.
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./macro_dashboard_api.db")

# ---------------------------------------------------------------------------
# JWT verification — pluggable so the issuer can be decided later.
#
# JWKS mode (RS256, e.g. Clerk or Supabase Auth in asymmetric mode):
#   JWT_JWKS_URL   — e.g. https://<issuer>/.well-known/jwks.json
#   JWT_ISSUER     — expected `iss` claim (optional, verified if set)
#   JWT_AUDIENCE   — expected `aud` claim (optional, verified if set)
#
# Shared-secret mode (HS256, e.g. Supabase Auth's default project JWT secret):
#   JWT_SECRET     — shared signing secret
#
# If neither is configured, auth falls back to dev-mode (see api/auth.py) —
# NOT safe to expose beyond localhost.
# ---------------------------------------------------------------------------
JWT_JWKS_URL = os.getenv("JWT_JWKS_URL", "")
JWT_ISSUER = os.getenv("JWT_ISSUER", "")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHMS = ["RS256", "HS256"]

# ---------------------------------------------------------------------------
# CORS — dashboard origin(s) allowed to call these APIs.
# ---------------------------------------------------------------------------
DASHBOARD_ORIGIN = os.getenv("DASHBOARD_ORIGIN", "")
DEV_ORIGIN = "http://localhost:3000"


def allowed_origins() -> list[str]:
    origins = [DEV_ORIGIN]
    if DASHBOARD_ORIGIN and DASHBOARD_ORIGIN not in origins:
        origins.append(DASHBOARD_ORIGIN)
    return origins
