from __future__ import annotations

"""User ORM model and role definitions."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.platform.database import Base


class UserRole(str, enum.Enum):
    """
    Platform RBAC roles.

    admin   -- Full access: manage users, all repositories, all analyses,
               audit logs, and system configuration.
    analyst -- Can register repositories, trigger analyses, read all reports,
               and use the chat/review APIs.
    viewer  -- Read-only access to repositories and reports they have been
               explicitly granted access to. Can use chat.
    """
    ADMIN   = "admin"
    ANALYST = "analyst"
    VIEWER  = "viewer"


class User(Base):
    """Platform user account."""

    __tablename__ = "users"

    id:              Mapped[int]      = mapped_column(Integer, primary_key=True, index=True)
    email:           Mapped[str]      = mapped_column(String(255), unique=True, index=True, nullable=False)
    username:        Mapped[str]      = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str]      = mapped_column(String(255), nullable=False)
    full_name:       Mapped[str]      = mapped_column(String(255), nullable=False, default="")
    role:            Mapped[str]      = mapped_column(
        Enum(UserRole, name="userrole", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=UserRole.VIEWER.value,
    )
    is_active:       Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True)
    created_at:      Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at:      Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now()
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    repositories: Mapped[list["Repository"]] = relationship(   # type: ignore[name-defined]
        "Repository", back_populates="owner", foreign_keys="Repository.owner_id"
    )
    access_grants: Mapped[list["RepositoryAccess"]] = relationship(   # type: ignore[name-defined]
        "RepositoryAccess",
        back_populates="user",
        foreign_keys="RepositoryAccess.user_id",
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(   # type: ignore[name-defined]
        "AuditLog", back_populates="user"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role}>"
