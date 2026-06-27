from __future__ import annotations

"""Phase 9: Pydantic request/response schemas — auth."""

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int  # seconds until access token expiry


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    email:     EmailStr
    username:  str       = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    password:  str       = Field(..., min_length=8, max_length=256)
    full_name: str       = Field("", max_length=255)
