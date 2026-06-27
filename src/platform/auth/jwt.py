from __future__ import annotations

"""
JWT token creation and verification for the RetroDecrypt Platform.

Two token types:
  access_token  -- short-lived (default 30 min), used for API authorisation.
  refresh_token -- long-lived (default 7 days), used only to obtain new access tokens.

Each token carries a JTI (JWT ID) that enables per-token revocation.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from src.platform.config import settings


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    subject: str,
    role:    str,
    extra:   Optional[dict] = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject: User identifier (username or user ID as string).
        role:    User's RBAC role.
        extra:   Optional additional claims merged into the payload.

    Returns:
        Signed JWT string.
    """
    expire = _now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub":  subject,
        "role": role,
        "type": "access",
        "jti":  str(uuid.uuid4()),
        "iat":  _now(),
        "exp":  expire,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """
    Create a signed JWT refresh token.

    Refresh tokens carry only the subject (username) and a JTI.
    They do NOT carry role information so they cannot be used for API access.
    """
    expire = _now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub":  subject,
        "type": "refresh",
        "jti":  str(uuid.uuid4()),
        "iat":  _now(),
        "exp":  expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------

class TokenData:
    """Decoded, validated token payload."""

    def __init__(self, payload: dict) -> None:
        self.subject:    str = payload["sub"]
        self.role:       str = payload.get("role", "viewer")
        self.token_type: str = payload.get("type", "access")
        self.jti:        str = payload.get("jti", "")


def decode_token(token: str, expected_type: str = "access") -> TokenData:
    """
    Decode and validate a JWT token.

    Args:
        token:         Raw JWT string.
        expected_type: "access" or "refresh".

    Returns:
        TokenData instance.

    Raises:
        JWTError: If the token is invalid, expired, or of the wrong type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError:
        raise

    if payload.get("type") != expected_type:
        raise JWTError(
            f"Token type mismatch: expected '{expected_type}', "
            f"got '{payload.get('type')}'"
        )

    if "sub" not in payload:
        raise JWTError("Token missing 'sub' claim")

    return TokenData(payload)
