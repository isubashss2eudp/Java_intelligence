from __future__ import annotations

"""Users router: /api/v1/users"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.platform.auth import get_current_user, require_admin
from src.platform.database import get_db
from src.platform.models.audit import AuditLog
from src.platform.models.user import User, UserRole
from src.platform.schemas.user import (
    PasswordChange, RoleUpdate, UserCreate, UserResponse, UserUpdate,
)
from src.platform.services import (
    audit_log, create_user, deactivate_user, get_user_or_404,
    list_users, update_role, update_user, change_password,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=List[UserResponse],
    summary="List all users (admin only)",
)
def list_all_users(
    offset:       int     = Query(0, ge=0),
    limit:        int     = Query(50, ge=1, le=200),
    db:           Session = Depends(get_db),
    _:            User    = Depends(require_admin),
) -> List[UserResponse]:
    users, _ = list_users(db, offset=offset, limit=limit)
    return users


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user (admin only)",
)
def create_new_user(
    body:          UserCreate,
    db:            Session = Depends(get_db),
    current_user:  User    = Depends(require_admin),
) -> UserResponse:
    user = create_user(db, body)
    audit_log(
        db,
        action=AuditLog.Actions.USER_CREATED,
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(user.id),
        details={"username": user.username, "role": user.role},
    )
    return user


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Return the current user's profile",
)
def get_my_profile(current_user: User = Depends(get_current_user)) -> UserResponse:
    return current_user


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Update the current user's profile",
)
def update_my_profile(
    body:         UserUpdate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> UserResponse:
    return update_user(db, current_user, body)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change the current user's password",
)
def change_my_password(
    body:         PasswordChange,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> None:
    change_password(db, current_user, body.current_password, body.new_password)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get a user by ID (admin only)",
)
def get_user(
    user_id: int,
    db:      Session = Depends(get_db),
    _:       User    = Depends(require_admin),
) -> UserResponse:
    return get_user_or_404(db, user_id)


@router.put(
    "/{user_id}/role",
    response_model=UserResponse,
    summary="Update a user's role (admin only)",
)
def set_user_role(
    user_id:      int,
    body:         RoleUpdate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_admin),
) -> UserResponse:
    user = get_user_or_404(db, user_id)
    updated = update_role(db, user, body.role)
    audit_log(
        db,
        action=AuditLog.Actions.ROLE_CHANGED,
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(user_id),
        details={"new_role": body.role.value},
    )
    return updated


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate a user (admin only)",
)
def deactivate(
    user_id:      int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_admin),
) -> None:
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )
    user = get_user_or_404(db, user_id)
    deactivate_user(db, user)
    audit_log(
        db,
        action=AuditLog.Actions.USER_DEACTIVATED,
        user_id=current_user.id,
        resource_type="user",
        resource_id=str(user_id),
    )
