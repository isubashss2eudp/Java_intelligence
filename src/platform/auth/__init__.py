from __future__ import annotations

"""Phase 9: Auth sub-package exports."""

from src.platform.auth.hashing import hash_password, verify_password
from src.platform.auth.jwt import create_access_token, create_refresh_token, decode_token, TokenData
from src.platform.auth.dependencies import (
    get_current_user,
    get_current_user_optional,
    require_role,
    require_admin,
    require_analyst,
    require_viewer,
)

__all__ = [
    "hash_password", "verify_password",
    "create_access_token", "create_refresh_token", "decode_token", "TokenData",
    "get_current_user", "get_current_user_optional",
    "require_role", "require_admin", "require_analyst", "require_viewer",
]
