from __future__ import annotations

"""Auth router: /api/v1/auth"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.orm import Session

from src.platform.auth import (
    create_access_token, create_refresh_token, decode_token,
    get_current_user,
)
from src.platform.config import settings
from src.platform.database import get_db
from src.platform.models.audit import AuditLog
from src.platform.models.user import UserRole
from src.platform.schemas.auth import (
    LoginRequest, RefreshRequest, RegisterRequest, TokenResponse,
)
from src.platform.schemas.user import UserResponse
from src.platform.services import audit_log, authenticate, create_user
from src.platform.schemas.user import UserCreate

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(
    body:    RegisterRequest,
    request: Request,
    db:      Session = Depends(get_db),
) -> UserResponse:
    """
    Create a new user account with the default viewer role.

    Admins can use POST /api/v1/users to create users with elevated roles.
    """
    user = create_user(db, UserCreate(
        email=body.email,
        username=body.username,
        password=body.password,
        full_name=body.full_name,
        role=UserRole(settings.DEFAULT_USER_ROLE),
    ))
    audit_log(
        db,
        action=AuditLog.Actions.USER_CREATED,
        user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        ip_address=_client_ip(request),
    )
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive JWT tokens",
)
def login(
    body:    LoginRequest,
    request: Request,
    db:      Session = Depends(get_db),
) -> TokenResponse:
    user = authenticate(db, body.username, body.password)
    if not user:
        audit_log(
            db,
            action=AuditLog.Actions.LOGIN_FAILED,
            details={"username": body.username},
            ip_address=_client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token  = create_access_token(user.username, user.role)
    refresh_token = create_refresh_token(user.username)

    audit_log(
        db,
        action=AuditLog.Actions.LOGIN,
        user_id=user.id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange a refresh token for a new access token",
)
def refresh_token(
    body: RefreshRequest,
    db:   Session = Depends(get_db),
) -> TokenResponse:
    try:
        token_data = decode_token(body.refresh_token, expected_type="refresh")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    from src.platform.services import get_user_by_username
    user = get_user_by_username(db, token_data.subject)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )

    access_token  = create_access_token(user.username, user.role)
    refresh_token_new = create_refresh_token(user.username)

    audit_log(db, action=AuditLog.Actions.TOKEN_REFRESH, user_id=user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_new,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout (client-side token discard)",
)
def logout(
    request:      Request,
    db:           Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> None:
    """
    Signals a logout.  Clients must discard stored tokens.
    Server-side JWT revocation requires a token blocklist (Redis / DB table)
    which is provisioned in Phase 10 (Redis deployment).
    """
    audit_log(
        db,
        action=AuditLog.Actions.LOGOUT,
        user_id=current_user.id,
        ip_address=_client_ip(request),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Return the current authenticated user's profile",
)
def get_me(current_user=Depends(get_current_user)) -> UserResponse:
    return current_user
