from __future__ import annotations

"""Phase 9: Pydantic schemas — users."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from src.platform.models.user import UserRole


class UserCreate(BaseModel):
    email:     EmailStr
    username:  str      = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    password:  str      = Field(..., min_length=8, max_length=256)
    full_name: str      = Field("", max_length=255)
    role:      UserRole = UserRole.VIEWER


class UserUpdate(BaseModel):
    full_name: Optional[str]  = Field(None, max_length=255)
    email:     Optional[EmailStr] = None


class PasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password:     str = Field(..., min_length=8, max_length=256)


class RoleUpdate(BaseModel):
    role: UserRole


class UserResponse(BaseModel):
    id:         int
    email:      str
    username:   str
    full_name:  str
    role:       str
    is_active:  bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserSummary(BaseModel):
    """Minimal user representation for embedding in other responses."""
    id:       int
    username: str
    role:     str

    model_config = {"from_attributes": True}
