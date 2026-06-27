from __future__ import annotations

"""
FastAPI dependency functions for authentication and RBAC.

Usage in route handlers:

    # Require any authenticated user
    def route(current_user: User = Depends(get_current_user)): ...

    # Require specific role
    def route(current_user: User = Depends(require_role(UserRole.ADMIN))): ...

    # Require admin
    def route(current_user: User = Depends(require_admin)): ...

    # Require analyst or above
    def route(current_user: User = Depends(require_analyst)): ...
"""

from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from src.platform.auth.jwt import decode_token
from src.platform.database import get_db
from src.platform.models.user import User, UserRole

_bearer = HTTPBearer(auto_error=True)

# Role ordering (higher index = more privileges)
_ROLE_ORDER = [UserRole.VIEWER.value, UserRole.ANALYST.value, UserRole.ADMIN.value]


def _role_gte(user_role: str, required_role: str) -> bool:
    """Return True if user_role has at least the privileges of required_role."""
    try:
        return _ROLE_ORDER.index(user_role) >= _ROLE_ORDER.index(required_role)
    except ValueError:
        return False


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """
    Decode the Bearer token and return the corresponding active User.

    Raises HTTP 401 if the token is invalid or the user does not exist / is inactive.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token_data = decode_token(credentials.credentials, expected_type="access")
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.username == token_data.subject).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_role(minimum_role: UserRole) -> Callable:
    """
    Returns a FastAPI dependency that enforces a minimum RBAC role.

    Example:
        @router.get("/admin-only")
        def admin_route(u: User = Depends(require_role(UserRole.ADMIN))): ...
    """
    def _dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if not _role_gte(current_user.role, minimum_role.value):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the '{minimum_role.value}' role or higher.",
            )
        return current_user

    return _dependency


# Convenience aliases
require_admin   = require_role(UserRole.ADMIN)
require_analyst = require_role(UserRole.ANALYST)
require_viewer  = require_role(UserRole.VIEWER)   # = any authenticated user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: Session = Depends(get_db),
) -> User | None:
    """
    Like get_current_user but returns None instead of raising 401 when no
    token is supplied (useful for endpoints that serve both auth and anon).
    """
    if credentials is None:
        return None
    try:
        token_data = decode_token(credentials.credentials, expected_type="access")
        user = db.query(User).filter(User.username == token_data.subject).first()
        if user and user.is_active:
            return user
    except JWTError:
        pass
    return None
