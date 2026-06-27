from __future__ import annotations

"""Code review router: /api/v1/review

On-demand code review for a specific repository and optional class list.
The review runs synchronously (small repo) or via background job (large repo).
"""

import json
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.platform.auth import get_current_user, require_analyst
from src.platform.config import settings
from src.platform.database import get_db
from src.platform.models.audit import AuditLog
from src.platform.models.repository import JobType
from src.platform.models.user import User
from src.platform.schemas.repository import JobResponse
from src.platform.services import (
    assert_can_read, audit_log, get_repository_or_404, repo_metadata_path,
    repo_review_path,
)
from src.platform.jobs.pipeline import create_job, run_job_background

router = APIRouter(prefix="/review", tags=["Code Review"])


class ReviewRequest(BaseModel):
    repository_id: int
    target_classes: Optional[List[str]] = None
    """If omitted all classes in the repository are reviewed."""


@router.post(
    "",
    summary="Trigger a code review job or return cached report",
)
def trigger_review(
    body:             ReviewRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db:               Session          = Depends(get_db),
    current_user:     User             = Depends(require_analyst),
) -> dict:
    """
    Run (or retrieve) a Phase 8 code review.

    If a report already exists it is returned immediately (HTTP 200).
    Otherwise a background job is created and HTTP 202 is returned.
    To force a re-run, delete the report via DELETE /repositories/{id}/review.
    """
    repo = get_repository_or_404(db, body.repository_id)
    assert_can_read(db, repo, current_user)

    report_path = repo_review_path(body.repository_id)

    # Return cached report if available (no target_classes filter)
    if report_path.exists() and not body.target_classes:
        audit_log(
            db, AuditLog.Actions.CODE_REVIEW, user_id=current_user.id,
            resource_type="repository", resource_id=str(body.repository_id),
            details={"cached": True},
        )
        return json.loads(report_path.read_text(encoding="utf-8"))

    # Run synchronously for targeted class reviews (fast path)
    if body.target_classes:
        meta_path = repo_metadata_path(body.repository_id)
        if not meta_path.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository has not been scanned yet. Run a scan first.",
            )
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            from src.code_review import CodeReviewEngine

            engine = CodeReviewEngine(repo_root=repo.local_path)
            report = engine.run(metadata, target_classes=body.target_classes)

            audit_log(
                db, AuditLog.Actions.CODE_REVIEW, user_id=current_user.id,
                resource_type="repository", resource_id=str(body.repository_id),
                details={"target_classes": body.target_classes, "findings": report.total_findings},
            )
            return report.to_json_report()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Code review failed: {exc}",
            )

    # Enqueue background job for full-repository review
    job = create_job(db, body.repository_id, JobType.CODE_REVIEW, current_user.id)
    background_tasks.add_task(
        run_job_background,
        job_id=job.id,
        db_url=settings.DATABASE_URL,
    )

    audit_log(
        db, AuditLog.Actions.CODE_REVIEW, user_id=current_user.id,
        resource_type="repository", resource_id=str(body.repository_id),
        details={"job_id": job.id, "status": "queued"},
    )

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "message": "Code review job queued.",
            "job_id": job.id,
            "repository_id": body.repository_id,
        },
    )


@router.delete(
    "/{repository_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a cached code review report (force re-run on next request)",
)
def delete_review_report(
    repository_id: int,
    db:            Session = Depends(get_db),
    current_user:  User    = Depends(require_analyst),
) -> None:
    repo = get_repository_or_404(db, repository_id)
    assert_can_read(db, repo, current_user)
    path = repo_review_path(repository_id)
    if path.exists():
        path.unlink()
