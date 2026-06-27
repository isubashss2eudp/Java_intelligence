from __future__ import annotations

"""
Phase 9: Enterprise Platform – FastAPI application factory.

Entry point for both development (uvicorn src.platform.main:app)
and production (gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.platform.main:app).
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.platform.api.v1 import api_router
from src.platform.config import settings
from src.platform.database import check_connection, create_all_tables

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bootstrap helpers
# ---------------------------------------------------------------------------

def _bootstrap_admin() -> None:
    """
    Create the initial admin user if the users table is empty.

    Uses PLATFORM_BOOTSTRAP_ADMIN_* env vars (see config.py).
    Skipped if any user already exists (idempotent on restarts).
    """
    if not (
        settings.BOOTSTRAP_ADMIN_EMAIL
        and settings.BOOTSTRAP_ADMIN_USERNAME
        and settings.BOOTSTRAP_ADMIN_PASSWORD
    ):
        logger.info("Bootstrap admin credentials not configured – skipping.")
        return

    from sqlalchemy.orm import Session
    from src.platform.database import SessionLocal
    from src.platform.models.user import User, UserRole
    from src.platform.schemas.user import UserCreate
    from src.platform.services.user_service import create_user

    with SessionLocal() as db:
        if db.query(User).count() > 0:
            return
        try:
            create_user(
                db,
                UserCreate(
                    email=settings.BOOTSTRAP_ADMIN_EMAIL,
                    username=settings.BOOTSTRAP_ADMIN_USERNAME,
                    password=settings.BOOTSTRAP_ADMIN_PASSWORD,
                    full_name="Platform Administrator",
                    role=UserRole.ADMIN,
                ),
            )
            logger.info(
                "Bootstrap admin '%s' created.",
                settings.BOOTSTRAP_ADMIN_USERNAME,
            )
        except Exception as exc:
            logger.warning("Bootstrap admin creation skipped: %s", exc)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle handler."""
    # Startup
    try:
        check_connection()
        logger.info("Database connection OK.")
    except Exception as exc:
        logger.error("Database connection failed: %s", exc)

    create_all_tables()
    logger.info("Database tables ready.")

    _bootstrap_admin()

    yield

    # Shutdown (nothing to clean up currently)
    logger.info("Platform shutting down.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="RetroDecrypt Platform",
        description=(
            "Enterprise-grade REST API for AI-powered Java repository analysis.\n\n"
            "Phases 1-9: metadata ingestion, vector search, dependency analysis, "
            "architecture detection, C4 diagrams, onboarding generation, "
            "multi-agent Q&A, code review, and enterprise platform management."
        ),
        version="9.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # CORS middleware
    # ------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception for %s %s: %s", request.method, request.url, exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred. Please try again later."},
        )

    # ------------------------------------------------------------------
    # Health check (no auth required)
    # ------------------------------------------------------------------
    @app.get("/health", tags=["Health"], summary="Service health check")
    def health_check() -> dict:
        return {
            "status": "healthy",
            "version": app.version,
            "service": "java-intelligence-platform",
        }

    # ------------------------------------------------------------------
    # API v1 routers
    # ------------------------------------------------------------------
    app.include_router(api_router, prefix="/api/v1")

    return app


# Module-level application instance for ASGI servers
app = create_app()
