from __future__ import annotations

"""
Phase 9: SQLAlchemy database engine and session management.

Uses synchronous SQLAlchemy (2.0 style) so that existing Phase 1-8
intelligence modules (LangChain, NetworkX, etc.) — which are all
synchronous — can be called directly from background tasks and services
without needing async wrappers.

FastAPI runs synchronous dependency functions in a thread pool
automatically when they are not declared async, so throughput is not
impacted.
"""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from typing import Generator

from src.platform.config import settings


# ---------------------------------------------------------------------------
# Declarative base — shared by all ORM models
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all platform models."""
    pass


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _build_engine(database_url: str):
    """
    Create a SQLAlchemy engine with sensible production defaults.

    SQLite (used in tests) and PostgreSQL (production) are both supported.
    Connection pool settings are tuned for an async-threaded FastAPI server.
    """
    connect_args = {}
    kwargs: dict = {}

    if database_url.startswith("sqlite"):
        # SQLite requires check_same_thread=False for FastAPI's thread pool
        connect_args["check_same_thread"] = False
        kwargs["pool_pre_ping"] = True
    else:
        # PostgreSQL production settings
        kwargs.update(
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
        )

    return create_engine(
        database_url,
        connect_args=connect_args,
        echo=settings.DEBUG,
        **kwargs,
    )


engine = _build_engine(settings.DATABASE_URL)

SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """
    Yield a SQLAlchemy session for the duration of a request.

    Usage in route handlers:
        def my_route(db: Session = Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Schema management helpers
# ---------------------------------------------------------------------------

def create_all_tables() -> None:
    """Create all tables defined in ORM models. Safe to call on startup."""
    # Import all models so their metadata is registered on Base
    import src.platform.models  # noqa: F401
    Base.metadata.create_all(bind=engine)


def drop_all_tables() -> None:
    """Drop all tables. Used in test teardown only."""
    import src.platform.models  # noqa: F401
    Base.metadata.drop_all(bind=engine)


def check_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
