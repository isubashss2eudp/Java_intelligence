from __future__ import annotations

"""Phase 9: Pydantic schemas — repositories, access grants, and analysis jobs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.platform.models.repository import JobStatus, JobType, RepoStatus


# ---------------------------------------------------------------------------
# Repository schemas
# ---------------------------------------------------------------------------

class RepositoryCreate(BaseModel):
    name:        str           = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2048)
    local_path:  str           = Field(..., min_length=1, max_length=1024)
    git_url:     Optional[str] = Field(None, max_length=1024)
    branch:      str           = Field("main", max_length=100)


class RepositoryUpdate(BaseModel):
    name:        Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2048)
    git_url:     Optional[str] = Field(None, max_length=1024)
    branch:      Optional[str] = Field(None, max_length=100)


class RepositoryResponse(BaseModel):
    id:              int
    name:            str
    description:     Optional[str]
    local_path:      str
    git_url:         Optional[str]
    branch:          str
    status:          str
    owner_id:        int
    last_scanned_at: Optional[datetime]
    file_count:      int
    class_count:     int
    error_message:   Optional[str]
    created_at:      datetime
    updated_at:      datetime

    model_config = {"from_attributes": True}


class RepositorySummary(BaseModel):
    """Lightweight listing view."""
    id:              int
    name:            str
    status:          str
    file_count:      int
    class_count:     int
    last_scanned_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Repository access grant schemas
# ---------------------------------------------------------------------------

class AccessGrantCreate(BaseModel):
    user_id:    int
    permission: str = Field("read", pattern=r"^(read|write|admin)$")


class AccessGrantResponse(BaseModel):
    id:            int
    repository_id: int
    user_id:       int
    permission:    str
    granted_by:    int
    created_at:    datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Analysis job schemas
# ---------------------------------------------------------------------------

class JobTriggerRequest(BaseModel):
    job_type: JobType = JobType.FULL_SCAN


class JobResponse(BaseModel):
    id:             int
    repository_id:  int
    job_type:       str
    status:         str
    result_summary: Optional[str]
    error_message:  Optional[str]
    created_by:     int
    started_at:     Optional[datetime]
    completed_at:   Optional[datetime]
    created_at:     datetime

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    """Paginated list of jobs."""
    items:  list[JobResponse]
    total:  int
    offset: int
    limit:  int
