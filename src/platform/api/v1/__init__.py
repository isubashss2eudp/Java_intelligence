from __future__ import annotations

"""API v1 sub-package: registers all routers."""

from fastapi import APIRouter

from src.platform.api.v1.auth         import router as auth_router
from src.platform.api.v1.users        import router as users_router
from src.platform.api.v1.repositories import router as repos_router
from src.platform.api.v1.chat         import router as chat_router
from src.platform.api.v1.review       import router as review_router
from src.platform.api.v1.audit        import router as audit_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(repos_router)
api_router.include_router(chat_router)
api_router.include_router(review_router)
api_router.include_router(audit_router)

__all__ = ["api_router"]
