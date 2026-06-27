from __future__ import annotations

"""Repositories router: /api/v1/repositories"""

import json
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.platform.auth import get_current_user, require_analyst, require_admin
from src.platform.config import settings
from src.platform.database import get_db
from src.platform.models.audit import AuditLog
from src.platform.models.repository import JobType
from src.platform.models.user import User
from src.platform.schemas.repository import (
    AccessGrantCreate, AccessGrantResponse,
    JobResponse, JobTriggerRequest,
    RepositoryCreate, RepositoryResponse, RepositorySummary, RepositoryUpdate,
)
from src.platform.services import (
    audit_log, assert_can_read, assert_can_write,
    create_repository, delete_repository, get_repository_or_404,
    grant_access, list_repositories, revoke_access,
    repo_metadata_path, repo_review_path, repo_onboarding_path, update_repository,
)
from src.platform.jobs.pipeline import create_job, list_jobs, run_job_background

router = APIRouter(prefix="/repositories", tags=["Repositories"])


# ---------------------------------------------------------------------------
# Repository CRUD
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new repository",
)
def register_repository(
    body:         RepositoryCreate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_analyst),
) -> RepositoryResponse:
    repo = create_repository(db, body, current_user)
    audit_log(
        db,
        action=AuditLog.Actions.REPO_REGISTERED,
        user_id=current_user.id,
        resource_type="repository",
        resource_id=str(repo.id),
        details={"name": repo.name, "path": repo.local_path},
    )
    return repo


@router.get(
    "",
    response_model=List[RepositorySummary],
    summary="List all accessible repositories",
)
def list_repos(
    offset:       int     = Query(0, ge=0),
    limit:        int     = Query(50, ge=1, le=200),
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> List[RepositorySummary]:
    repos, _ = list_repositories(db, current_user, offset=offset, limit=limit)
    return repos


@router.get(
    "/{repo_id}",
    response_model=RepositoryResponse,
    summary="Get repository details",
)
def get_repo(
    repo_id:      int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> RepositoryResponse:
    repo = get_repository_or_404(db, repo_id)
    assert_can_read(db, repo, current_user)
    return repo


@router.put(
    "/{repo_id}",
    response_model=RepositoryResponse,
    summary="Update repository metadata",
)
def update_repo(
    repo_id:      int,
    body:         RepositoryUpdate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> RepositoryResponse:
    repo = get_repository_or_404(db, repo_id)
    assert_can_write(db, repo, current_user)
    return update_repository(db, repo, body)


@router.delete(
    "/{repo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a repository and all its data (admin only)",
)
def delete_repo(
    repo_id:      int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(require_admin),
) -> None:
    repo = get_repository_or_404(db, repo_id)
    audit_log(
        db,
        action=AuditLog.Actions.REPO_DELETED,
        user_id=current_user.id,
        resource_type="repository",
        resource_id=str(repo_id),
        details={"name": repo.name},
        commit=False,
    )
    delete_repository(db, repo)


# ---------------------------------------------------------------------------
# Analysis jobs
# ---------------------------------------------------------------------------

@router.post(
    "/{repo_id}/scan",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a repository analysis job",
)
def trigger_scan(
    repo_id:          int,
    body:             JobTriggerRequest = JobTriggerRequest(),
    background_tasks: BackgroundTasks   = BackgroundTasks(),
    db:               Session = Depends(get_db),
    current_user:     User    = Depends(require_analyst),
) -> JobResponse:
    """
    Enqueue a background analysis job.

    Returns HTTP 202 immediately with the job record.
    Poll GET /api/v1/repositories/{repo_id}/jobs/{job_id} for status.
    """
    repo = get_repository_or_404(db, repo_id)
    assert_can_write(db, repo, current_user)

    job = create_job(db, repo_id, body.job_type, current_user.id)

    # Dispatch background task with its own DB session
    background_tasks.add_task(
        run_job_background,
        job_id=job.id,
        db_url=settings.DATABASE_URL,
    )

    audit_log(
        db,
        action=AuditLog.Actions.REPO_SCAN_STARTED,
        user_id=current_user.id,
        resource_type="repository",
        resource_id=str(repo_id),
        details={"job_id": job.id, "job_type": body.job_type.value},
    )
    return job


@router.get(
    "/{repo_id}/jobs",
    response_model=List[JobResponse],
    summary="List analysis jobs for a repository",
)
def list_repo_jobs(
    repo_id:      int,
    offset:       int     = Query(0, ge=0),
    limit:        int     = Query(50, ge=1, le=200),
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> List[JobResponse]:
    repo = get_repository_or_404(db, repo_id)
    assert_can_read(db, repo, current_user)
    jobs, _ = list_jobs(db, repo_id=repo_id, offset=offset, limit=limit)
    return jobs


# ---------------------------------------------------------------------------
# Analysis results
# ---------------------------------------------------------------------------

@router.get(
    "/{repo_id}/metadata",
    summary="Return raw repository metadata (Phase 1 output)",
)
def get_metadata(
    repo_id:      int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> dict:
    repo = get_repository_or_404(db, repo_id)
    assert_can_read(db, repo, current_user)
    path = repo_metadata_path(repo_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Metadata not available. Run a scan first.")
    audit_log(db, AuditLog.Actions.REPORT_ACCESSED, user_id=current_user.id,
              resource_type="repository", resource_id=str(repo_id),
              details={"report": "metadata"})
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"repository_id": repo_id, "file_count": len(data), "files": data[:100]}


@router.get(
    "/{repo_id}/review",
    summary="Return the Phase 8 code review report",
)
def get_review_report(
    repo_id:      int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> dict:
    repo = get_repository_or_404(db, repo_id)
    assert_can_read(db, repo, current_user)
    path = repo_review_path(repo_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Code review report not available. Run a scan first.")
    audit_log(db, AuditLog.Actions.REPORT_ACCESSED, user_id=current_user.id,
              resource_type="repository", resource_id=str(repo_id),
              details={"report": "code_review"})
    return json.loads(path.read_text(encoding="utf-8"))


@router.get(
    "/{repo_id}/onboarding",
    summary="Return the generated onboarding documentation",
)
def get_onboarding(
    repo_id:      int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> dict:
    repo = get_repository_or_404(db, repo_id)
    assert_can_read(db, repo, current_user)
    path = repo_onboarding_path(repo_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Onboarding doc not available. Run a scan first.")
    audit_log(db, AuditLog.Actions.REPORT_ACCESSED, user_id=current_user.id,
              resource_type="repository", resource_id=str(repo_id),
              details={"report": "onboarding"})
    return {"repository_id": repo_id, "content": path.read_text(encoding="utf-8")}


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

@router.post(
    "/{repo_id}/access",
    response_model=AccessGrantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Grant a user access to a repository",
)
def grant_repo_access(
    repo_id:      int,
    body:         AccessGrantCreate,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> AccessGrantResponse:
    repo = get_repository_or_404(db, repo_id)
    assert_can_write(db, repo, current_user)
    access = grant_access(db, repo_id, body.user_id, body.permission, current_user.id)
    audit_log(
        db, AuditLog.Actions.ACCESS_GRANTED, user_id=current_user.id,
        resource_type="repository", resource_id=str(repo_id),
        details={"target_user": body.user_id, "permission": body.permission},
    )
    return access


@router.delete(
    "/{repo_id}/access/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a user's access to a repository",
)
def revoke_repo_access(
    repo_id:      int,
    user_id:      int,
    db:           Session = Depends(get_db),
    current_user: User    = Depends(get_current_user),
) -> None:
    repo = get_repository_or_404(db, repo_id)
    assert_can_write(db, repo, current_user)
    revoke_access(db, repo_id, user_id)
    audit_log(
        db, AuditLog.Actions.ACCESS_REVOKED, user_id=current_user.id,
        resource_type="repository", resource_id=str(repo_id),
        details={"target_user": user_id},
    )
