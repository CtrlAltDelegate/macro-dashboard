"""SQLAlchemy engine/session setup. Portable between local SQLite (dev) and
Supabase/any Postgres (prod) via DATABASE_URL — see api/config.py."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from . import config

_connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a request-scoped session, always closed after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they don't exist. Safe to call repeatedly."""
    from . import models_db  # noqa: F401 (registers models on Base.metadata)
    Base.metadata.create_all(bind=engine)


@contextmanager
def _short_lived_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def db_is_reachable() -> bool:
    """Used by GET /health — returns False (never raises) if the DB can't be reached."""
    try:
        with _short_lived_session() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
