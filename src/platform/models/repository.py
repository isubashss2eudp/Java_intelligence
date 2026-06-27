from __future__ import annotations

"""Repository, RepositoryAccess, and AnalysisJob ORM models."""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.platform.database import Base


# ---------------------------------------------------------------------------
# Enum types
# ---------------------------------------------------------------------------

class RepoStatus(str, enum.Enum):
    """Lifecycle status of a registered repository."""
    REGISTERED = "registered"   # just created, not yet scanned
    SCANNING   = "scanning"     # scan in progress
    READY      = "ready"        # fully indexed and ready for queries
    ERROR      = "error"        # scan failed; error_message holds details
    UPDATING   = "updating"     # incremental update in progress


class JobType(str, enum.Enum):
    """Type of background analysis job."""
    FULL_SCAN     = "full_scan"      # end-to-end: metadata → vector → dep → arch → review
    METADATA      = "metadata"       # Phase 1: repository scan + metadata extraction
    VECTOR_INDEX  = "vector_index"   # Phase 2: build/refresh vector database
    DEPENDENCY    = "dependency"     # Phase 4: build dependency graph
    ARCHITECTURE  = "architecture"   # Phase 5: architecture analysis + onboarding doc
    CODE_REVIEW   = "code_review"    # Phase 8: static code review


class JobStatus(str, enum.Enum):
    """Runtime status of a background job."""
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class Repository(Base):
    """A registered Java/Spring Boot repository."""

    __tablename__ = "repositories"

    id:              Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    name:            Mapped[str]           = mapped_column(String(255), nullable=False, index=True)
    description:     Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    local_path:      Mapped[str]           = mapped_column(String(1024), nullable=False)
    git_url:         Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    branch:          Mapped[str]           = mapped_column(String(100), nullable=False, default="main")
    status:          Mapped[str]           = mapped_column(
        Enum(RepoStatus, name="repostatus", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=RepoStatus.REGISTERED.value,
    )
    owner_id:        Mapped[int]           = mapped_column(ForeignKey("users.id"), nullable=False)
    last_scanned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    file_count:      Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    class_count:     Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    error_message:   Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:      Mapped[datetime]      = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at:      Mapped[datetime]      = mapped_column(
        DateTime, nullable=False, default=func.now(), onupdate=func.now()
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    owner:   Mapped["User"] = relationship(     # type: ignore[name-defined]
        "User", back_populates="repositories", foreign_keys=[owner_id]
    )
    access_grants: Mapped[list["RepositoryAccess"]] = relationship(
        "RepositoryAccess", back_populates="repository",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob", back_populates="repository",
        cascade="all, delete-orphan",
        order_by="AnalysisJob.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<Repository id={self.id} name={self.name!r} status={self.status}>"


# ---------------------------------------------------------------------------
# RepositoryAccess  (fine-grained per-user per-repo RBAC)
# ---------------------------------------------------------------------------

class RepositoryAccess(Base):
    """
    Grants a specific user access to a repository.

    Admins implicitly have access to all repos.
    Analysts and Viewers require an explicit grant to access non-owned repos.
    """

    __tablename__ = "repository_access"

    id:            Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    user_id:       Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    permission:    Mapped[str] = mapped_column(
        String(50), nullable=False, default="read"
    )  # read | write | admin
    granted_by:    Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at:    Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    repository: Mapped["Repository"] = relationship(
        "Repository", back_populates="access_grants"
    )
    user: Mapped["User"] = relationship(    # type: ignore[name-defined]
        "User", back_populates="access_grants", foreign_keys=[user_id]
    )

    def __repr__(self) -> str:
        return (
            f"<RepositoryAccess repo={self.repository_id} "
            f"user={self.user_id} perm={self.permission}>"
        )


# ---------------------------------------------------------------------------
# AnalysisJob
# ---------------------------------------------------------------------------

class AnalysisJob(Base):
    """
    Tracks a background analysis job for a repository.

    Each job is a discrete unit of work (metadata scan, vector indexing,
    dependency analysis, etc.) that runs asynchronously and whose progress
    can be polled via the API.
    """

    __tablename__ = "analysis_jobs"

    id:             Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    repository_id:  Mapped[int]           = mapped_column(ForeignKey("repositories.id"), nullable=False)
    job_type:       Mapped[str]           = mapped_column(
        Enum(JobType, name="jobtype", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    status:         Mapped[str]           = mapped_column(
        Enum(JobStatus, name="jobstatus", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=JobStatus.PENDING.value,
    )
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message:  Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by:     Mapped[int]           = mapped_column(ForeignKey("users.id"), nullable=False)
    started_at:     Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at:   Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at:     Mapped[datetime]      = mapped_column(DateTime, nullable=False, default=func.now())

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    repository: Mapped["Repository"] = relationship("Repository", back_populates="jobs")
    creator:    Mapped["User"]       = relationship(   # type: ignore[name-defined]
        "User", foreign_keys=[created_by]
    )

    def __repr__(self) -> str:
        return (
            f"<AnalysisJob id={self.id} repo={self.repository_id} "
            f"type={self.job_type} status={self.status}>"
        )
