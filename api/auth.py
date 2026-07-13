"""
Pluggable JWT auth. Verifies Bearer tokens via JWKS (RS256) or a shared secret
(HS256) — whichever is configured via env vars, see api/config.py. Extracts
user_id from the standard `sub` claim (used by both Clerk and Supabase Auth),
so swapping the issuer later is just an env var change, per the spec.

If neither JWT_JWKS_URL nor JWT_SECRET is set, falls back to dev-mode: decodes
the token without verifying its signature. That keeps local development
unblocked before an issuer is chosen, but must never be used past localhost.
"""
from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config

_bearer = HTTPBearer(auto_error=False)
_jwks_client = jwt.PyJWKClient(config.JWT_JWKS_URL) if config.JWT_JWKS_URL else None


def _decode(token: str) -> dict:
    verify_aud = bool(config.JWT_AUDIENCE)
    verify_iss = bool(config.JWT_ISSUER)
    options = {"verify_aud": verify_aud, "verify_iss": verify_iss}

    if _jwks_client is not None:
        signing_key = _jwks_client.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=config.JWT_AUDIENCE or None,
            issuer=config.JWT_ISSUER or None,
            options=options,
        )
    if config.JWT_SECRET:
        return jwt.decode(
            token,
            config.JWT_SECRET,
            algorithms=["HS256"],
            audience=config.JWT_AUDIENCE or None,
            issuer=config.JWT_ISSUER or None,
            options=options,
        )
    return jwt.decode(token, options={"verify_signature": False})


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """FastAPI dependency for all protected routes. Raises 401 on any auth failure."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        claims = _decode(credentials.credentials)
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing 'sub' claim")
    return str(user_id)
