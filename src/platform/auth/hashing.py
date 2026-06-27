from __future__ import annotations

"""
Password hashing using bcrypt directly.

passlib is not compatible with bcrypt >= 4.x so we use the bcrypt library
directly. Passwords are UTF-8 encoded and truncated to 72 bytes (bcrypt max).
"""

import bcrypt


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the plaintext password."""
    pw_bytes = plain.encode("utf-8")[:72]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if the plaintext password matches the stored hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except Exception:
        return False
