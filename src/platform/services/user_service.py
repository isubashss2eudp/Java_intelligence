from __future__ import annotations

"""User CRUD service."""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.platform.auth.hashing import hash_password, verify_password
from src.platform.models.user import User, UserRole
from src.platform.schemas.user import UserCreate, UserUpdate


def create_user(db: Session, data: UserCreate) -> User:
    """
    Create a new platform user.

    Raises HTTP 409 if the email or username is already taken.
    """
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{data.email}' is already registered.",
        )
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{data.username}' is already taken.",
        )

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role.value,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def get_user_or_404(db: Session, user_id: int) -> User:
    user = get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found.",
        )
    return user


def list_users(
    db:     Session,
    offset: int = 0,
    limit:  int = 50,
) -> tuple[list[User], int]:
    q     = db.query(User)
    total = q.count()
    items = q.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    return items, total


def update_user(db: Session, user: User, data: UserUpdate) -> User:
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.email is not None:
        conflict = db.query(User).filter(
            User.email == data.email, User.id != user.id
        ).first()
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email '{data.email}' is already in use.",
            )
        user.email = data.email
    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    user.hashed_password = hash_password(new)
    db.commit()


def update_role(db: Session, user: User, new_role: UserRole) -> User:
    user.role = new_role.value
    db.commit()
    db.refresh(user)
    return user


def deactivate_user(db: Session, user: User) -> None:
    user.is_active = False
    db.commit()


def authenticate(db: Session, username: str, password: str) -> Optional[User]:
    """Return the User if credentials are valid, else None."""
    user = get_user_by_username(db, username)
    if user and user.is_active and verify_password(password, user.hashed_password):
        return user
    return None
