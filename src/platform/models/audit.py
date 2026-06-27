from __future__ import annotations

"""AuditLog ORM model — immutable record of platform events."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.platform.database import Base


class AuditLog(Base):
    """
    Immutable audit trail entry.

    Every significant action (login, repository scan, chat query, etc.)
    is appended here. Records are never updated or deleted.
    """

    __tablename__ = "audit_logs"

    id:            Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    user_id:       Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    action:        Mapped[str]           = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resource_id:   Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    details:       Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON blob
    ip_address:    Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent:    Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at:    Mapped[datetime]      = mapped_column(
        DateTime, nullable=False, default=func.now(), index=True
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped[Optional["User"]] = relationship(   # type: ignore[name-defined]
        "User", back_populates="audit_logs"
    )

    # ------------------------------------------------------------------
    # Audit action constants (not an enum — extensible without migration)
    # ------------------------------------------------------------------
    class Actions:
        LOGIN              = "LOGIN"
        LOGOUT             = "LOGOUT"
        LOGIN_FAILED       = "LOGIN_FAILED"
        TOKEN_REFRESH      = "TOKEN_REFRESH"
        USER_CREATED       = "USER_CREATED"
        USER_UPDATED       = "USER_UPDATED"
        USER_DEACTIVATED   = "USER_DEACTIVATED"
        ROLE_CHANGED       = "ROLE_CHANGED"
        REPO_REGISTERED    = "REPO_REGISTERED"
        REPO_DELETED       = "REPO_DELETED"
        REPO_SCAN_STARTED  = "REPO_SCAN_STARTED"
        REPO_SCAN_COMPLETE = "REPO_SCAN_COMPLETE"
        REPO_SCAN_FAILED   = "REPO_SCAN_FAILED"
        ACCESS_GRANTED     = "ACCESS_GRANTED"
        ACCESS_REVOKED     = "ACCESS_REVOKED"
        CHAT_QUERY         = "CHAT_QUERY"
        CODE_REVIEW        = "CODE_REVIEW"
        REPORT_ACCESSED    = "REPORT_ACCESSED"

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} action={self.action!r} "
            f"user_id={self.user_id} at={self.created_at}>"
        )
