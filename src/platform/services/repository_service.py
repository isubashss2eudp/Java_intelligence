from __future__ import annotations

"""
Repository CRUD service.

Handles registration, metadata updates, access control, and
the per-repository data directory layout for multi-repo support.

Per-repository directory layout (under REPOSITORIES_DATA_DIR):
  {data_dir}/{repo_id}/
    metadata.json          Phase 1 output
    dependency_graph.json  Phase 4 output
    dependency_adjacency.json
    architecture_report.json
    architecture_diagrams.md
    onboarding.md
    code_review_report.json  Phase 8 output
    vectordb/               Phase 2 ChromaDB collection
"""

import shutil
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.platform.config import settings
from src.platform.models.repository import (
    AnalysisJob, Repository, RepositoryAccess, RepoStatus,
)
from src.platform.models.user import User, UserRole
from src.platform.schemas.repository import RepositoryCreate, RepositoryUpdate


# ---------------------------------------------------------------------------
# Per-repository path helpers
# ---------------------------------------------------------------------------

def repo_data_dir(repo_id: int) -> Path:
    """Return the data directory for a repository, creating it if needed."""
    p = Path(settings.REPOSITORIES_DATA_DIR) / str(repo_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def repo_vectordb_dir(repo_id: int) -> Path:
    p = repo_data_dir(repo_id) / "vectordb"
    p.mkdir(parents=True, exist_ok=True)
    return p


def repo_metadata_path(repo_id: int) -> Path:
    return repo_data_dir(repo_id) / "metadata.json"


def repo_dep_graph_path(repo_id: int) -> Path:
    return repo_data_dir(repo_id) / "dependency_graph.json"


def repo_onboarding_path(repo_id: int) -> Path:
    return repo_data_dir(repo_id) / "onboarding.md"


def repo_review_path(repo_id: int) -> Path:
    return repo_data_dir(repo_id) / "code_review_report.json"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_repository(db: Session, data: RepositoryCreate, owner: User) -> Repository:
    """Register a new repository."""
    path = Path(data.local_path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path does not exist: {data.local_path}",
        )

    repo = Repository(
        name=data.name,
        description=data.description,
        local_path=str(path.resolve()),
        git_url=data.git_url,
        branch=data.branch,
        status=RepoStatus.REGISTERED.value,
        owner_id=owner.id,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)

    # Bootstrap the data directory
    repo_data_dir(repo.id)

    return repo


def get_repository(db: Session, repo_id: int) -> Optional[Repository]:
    return db.query(Repository).filter(Repository.id == repo_id).first()


def get_repository_or_404(db: Session, repo_id: int) -> Repository:
    repo = get_repository(db, repo_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository {repo_id} not found.",
        )
    return repo


def list_repositories(
    db:      Session,
    user:    User,
    offset:  int = 0,
    limit:   int = 50,
) -> tuple[list[Repository], int]:
    """
    List repositories visible to the requesting user.

    - Admin sees all repositories.
    - Others see repositories they own or have an explicit access grant for.
    """
    q = db.query(Repository)
    if user.role != UserRole.ADMIN.value:
        accessible_ids = [
            ra.repository_id
            for ra in db.query(RepositoryAccess).filter(
                RepositoryAccess.user_id == user.id
            ).all()
        ]
        q = q.filter(
            (Repository.owner_id == user.id) |
            (Repository.id.in_(accessible_ids))
        )

    total = q.count()
    items = q.order_by(Repository.created_at.desc()).offset(offset).limit(limit).all()
    return items, total


def update_repository(
    db:   Session,
    repo: Repository,
    data: RepositoryUpdate,
) -> Repository:
    if data.name is not None:
        repo.name = data.name
    if data.description is not None:
        repo.description = data.description
    if data.git_url is not None:
        repo.git_url = data.git_url
    if data.branch is not None:
        repo.branch = data.branch
    db.commit()
    db.refresh(repo)
    return repo


def delete_repository(db: Session, repo: Repository) -> None:
    """Delete a repository and all its data on disk."""
    data_dir = Path(settings.REPOSITORIES_DATA_DIR) / str(repo.id)
    if data_dir.exists():
        shutil.rmtree(data_dir, ignore_errors=True)
    db.delete(repo)
    db.commit()


# ---------------------------------------------------------------------------
# Access control helpers
# ---------------------------------------------------------------------------

def assert_can_read(db: Session, repo: Repository, user: User) -> None:
    """Raise HTTP 403 if the user cannot read this repository."""
    if user.role == UserRole.ADMIN.value:
        return
    if repo.owner_id == user.id:
        return
    grant = db.query(RepositoryAccess).filter(
        RepositoryAccess.repository_id == repo.id,
        RepositoryAccess.user_id == user.id,
    ).first()
    if not grant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this repository.",
        )


def assert_can_write(db: Session, repo: Repository, user: User) -> None:
    """Raise HTTP 403 if the user cannot write (trigger analysis, update) this repository."""
    if user.role == UserRole.ADMIN.value:
        return
    if repo.owner_id == user.id:
        return
    grant = db.query(RepositoryAccess).filter(
        RepositoryAccess.repository_id == repo.id,
        RepositoryAccess.user_id == user.id,
        RepositoryAccess.permission.in_(["write", "admin"]),
    ).first()
    if not grant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have write access to this repository.",
        )


def grant_access(
    db:            Session,
    repo_id:       int,
    user_id:       int,
    permission:    str,
    granted_by_id: int,
) -> RepositoryAccess:
    existing = db.query(RepositoryAccess).filter(
        RepositoryAccess.repository_id == repo_id,
        RepositoryAccess.user_id == user_id,
    ).first()
    if existing:
        existing.permission = permission
        existing.granted_by = granted_by_id
        db.commit()
        db.refresh(existing)
        return existing

    access = RepositoryAccess(
        repository_id=repo_id,
        user_id=user_id,
        permission=permission,
        granted_by=granted_by_id,
    )
    db.add(access)
    db.commit()
    db.refresh(access)
    return access


def revoke_access(db: Session, repo_id: int, user_id: int) -> None:
    db.query(RepositoryAccess).filter(
        RepositoryAccess.repository_id == repo_id,
        RepositoryAccess.user_id == user_id,
    ).delete()
    db.commit()
