from __future__ import annotations

"""
Background analysis job pipeline for Phase 9.

Each analysis job is a discrete unit of work that:
  1. Is created as an AnalysisJob row with status=PENDING.
  2. Runs in a FastAPI BackgroundTask (thread pool).
  3. Updates its own status row to RUNNING → COMPLETED/FAILED.
  4. Stores result summaries in the per-repo data directory.

Job types map to Phase 1-8 modules:
  FULL_SCAN     → metadata + vector_index + dependency + architecture + code_review
  METADATA      → Phase 1: ingest_repository()
  VECTOR_INDEX  → Phase 2: build_vector_store()
  DEPENDENCY    → Phase 4: build_full_graph()
  ARCHITECTURE  → Phase 5: analyze_architecture()
  CODE_REVIEW   → Phase 8: CodeReviewEngine.run()
"""

import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from src.platform.config import settings
from src.platform.models.repository import (
    AnalysisJob, JobStatus, JobType, Repository, RepoStatus,
)
from src.platform.services.repository_service import (
    repo_data_dir, repo_dep_graph_path, repo_metadata_path,
    repo_onboarding_path, repo_review_path, repo_vectordb_dir,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job creation
# ---------------------------------------------------------------------------

def create_job(
    db:            Session,
    repo_id:       int,
    job_type:      JobType,
    created_by_id: int,
) -> AnalysisJob:
    """Create an AnalysisJob record and return it (status=PENDING)."""
    job = AnalysisJob(
        repository_id=repo_id,
        job_type=job_type.value,
        status=JobStatus.PENDING.value,
        created_by=created_by_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: int) -> Optional[AnalysisJob]:
    return db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()


def list_jobs(
    db:      Session,
    repo_id: Optional[int] = None,
    offset:  int = 0,
    limit:   int = 50,
) -> tuple[list[AnalysisJob], int]:
    q = db.query(AnalysisJob)
    if repo_id is not None:
        q = q.filter(AnalysisJob.repository_id == repo_id)
    total = q.count()
    items = q.order_by(AnalysisJob.created_at.desc()).offset(offset).limit(limit).all()
    return items, total


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------

def run_job_background(
    job_id:   int,
    db_url:   str,
) -> None:
    """
    Execute a single analysis job.

    This function runs in a FastAPI BackgroundTask (thread pool) so it
    must NOT use the request-scoped database session. Instead it opens
    its own session using the provided database URL.
    """
    # Open a dedicated DB session for this background task
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    connect_args = {"check_same_thread": False} if db_url.startswith("sqlite") else {}
    _engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
    _Session = sessionmaker(bind=_engine)

    with _Session() as db:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if not job:
            logger.error("Job %d not found", job_id)
            return

        repo = db.query(Repository).filter(Repository.id == job.repository_id).first()
        if not repo:
            _mark_failed(db, job, f"Repository {job.repository_id} not found")
            return

        _mark_running(db, job, repo)

        try:
            summary = _execute_job(job.job_type, repo, db)
            _mark_completed(db, job, repo, summary)
        except Exception as exc:
            err = traceback.format_exc()
            logger.error("Job %d failed: %s", job_id, err)
            _mark_failed(db, job, str(exc), repo)


# ---------------------------------------------------------------------------
# Job execution dispatcher
# ---------------------------------------------------------------------------

def _execute_job(job_type: str, repo: Repository, db: Session) -> str:
    """Dispatch to the appropriate Phase module and return a summary string."""
    repo_id   = repo.id
    repo_path = repo.local_path

    if job_type == JobType.METADATA.value:
        return _run_metadata(repo_id, repo_path)

    elif job_type == JobType.VECTOR_INDEX.value:
        return _run_vector_index(repo_id)

    elif job_type == JobType.DEPENDENCY.value:
        return _run_dependency(repo_id)

    elif job_type == JobType.ARCHITECTURE.value:
        return _run_architecture(repo_id)

    elif job_type == JobType.CODE_REVIEW.value:
        return _run_code_review(repo_id)

    elif job_type == JobType.FULL_SCAN.value:
        # Sequential pipeline: each step feeds the next
        s1 = _run_metadata(repo_id, repo_path)
        _update_repo_stats(db, repo, repo_id)
        s2 = _run_vector_index(repo_id)
        s3 = _run_dependency(repo_id)
        s4 = _run_architecture(repo_id)
        s5 = _run_code_review(repo_id)
        return f"FULL SCAN: {s1} | {s2} | {s3} | {s4} | {s5}"

    else:
        raise ValueError(f"Unknown job type: {job_type}")


# ---------------------------------------------------------------------------
# Phase-specific runners
# ---------------------------------------------------------------------------

def _run_metadata(repo_id: int, repo_path: str) -> str:
    """Phase 1: scan and parse all Java files."""
    from src.ingest import ingest_repository

    data = ingest_repository(repo_path)
    out_path = repo_metadata_path(repo_id)
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return f"metadata: {len(data)} files"


def _run_vector_index(repo_id: int) -> str:
    """Phase 2: build or refresh the vector database."""
    meta_path = repo_metadata_path(repo_id)
    if not meta_path.exists():
        raise FileNotFoundError("metadata.json not found — run metadata job first")

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    from src.embeddings import load_embeddings
    from src.chunker import build_documents
    from src.vector_store import build_vector_store as _build_vs
    from langchain_chroma import Chroma

    embeddings = load_embeddings()
    documents  = build_documents(metadata)

    # Use per-repo collection name to support multi-repository indexing
    collection_name = f"repo_{repo_id}"
    vectordb_dir    = str(repo_vectordb_dir(repo_id))

    # Import Chroma directly for per-repo store
    from langchain_chroma import Chroma as ChromaStore
    import hashlib

    ids = [
        hashlib.md5(
            (doc.metadata.get("file", "") +
             doc.metadata.get("chunk_type", "") +
             str(doc.metadata.get("chunk_index", 0))).encode()
        ).hexdigest()
        for doc in documents
    ]

    store = ChromaStore(
        collection_name=collection_name,
        persist_directory=vectordb_dir,
        embedding_function=embeddings,
    )
    batch = 500
    for i in range(0, len(documents), batch):
        store.add_documents(
            documents[i:i+batch],
            ids=ids[i:i+batch],
        )

    return f"vector_index: {len(documents)} chunks"


def _run_dependency(repo_id: int) -> str:
    """Phase 4: build dependency graph."""
    meta_path = repo_metadata_path(repo_id)
    if not meta_path.exists():
        raise FileNotFoundError("metadata.json not found — run metadata job first")

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    from src.dependency import build_full_graph
    from src.dependency.exporter import save_json

    G = build_full_graph(metadata)
    out_path = repo_dep_graph_path(repo_id)
    save_json(G, str(out_path))

    return f"dependency: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges"


def _run_architecture(repo_id: int) -> str:
    """Phase 5: architecture analysis and onboarding doc."""
    meta_path = repo_metadata_path(repo_id)
    if not meta_path.exists():
        raise FileNotFoundError("metadata.json not found — run metadata job first")

    metadata  = json.loads(meta_path.read_text(encoding="utf-8"))
    data_dir  = repo_data_dir(repo_id)

    from src.architecture import analyze_architecture
    from src.architecture.onboarding import generate_onboarding
    from src.architecture.diagram import all_diagrams

    report = analyze_architecture(metadata)

    # Save architecture report
    arch_path = data_dir / "architecture_report.json"
    arch_path.write_text(
        json.dumps(report.to_dict() if hasattr(report, "to_dict") else {}, indent=2),
        encoding="utf-8",
    )

    # Save onboarding doc
    onboarding = generate_onboarding(report)
    repo_onboarding_path(repo_id).write_text(onboarding, encoding="utf-8")

    # Save diagrams
    diagrams = all_diagrams(report)
    (data_dir / "architecture_diagrams.md").write_text(diagrams, encoding="utf-8")

    layer_count = len(report.layers) if hasattr(report, "layers") else 0
    return f"architecture: {layer_count} layers"


def _run_code_review(repo_id: int) -> str:
    """Phase 8: static code review."""
    meta_path = repo_metadata_path(repo_id)
    if not meta_path.exists():
        raise FileNotFoundError("metadata.json not found — run metadata job first")

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    from src.code_review import CodeReviewEngine

    engine = CodeReviewEngine(repo_root=metadata[0].get("file_path", "").split("/")[0] if metadata else "")
    report = engine.run(metadata)

    # Save JSON report
    out = repo_review_path(repo_id)
    out.write_text(
        json.dumps(report.to_json_report(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return (
        f"code_review: {report.total_findings} findings, "
        f"score={report.quality_score:.1f}, grade={report.grade}"
    )


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def _mark_running(db: Session, job: AnalysisJob, repo: Repository) -> None:
    job.status     = JobStatus.RUNNING.value
    job.started_at = datetime.now(timezone.utc)
    repo.status    = RepoStatus.SCANNING.value
    db.commit()


def _mark_completed(
    db:      Session,
    job:     AnalysisJob,
    repo:    Repository,
    summary: str,
) -> None:
    now = datetime.now(timezone.utc)
    job.status          = JobStatus.COMPLETED.value
    job.completed_at    = now
    job.result_summary  = summary
    repo.status         = RepoStatus.READY.value
    repo.last_scanned_at = now
    repo.error_message  = None
    _update_repo_stats(db, repo, repo.id)
    db.commit()


def _mark_failed(
    db:    Session,
    job:   AnalysisJob,
    error: str,
    repo:  Optional[Repository] = None,
) -> None:
    job.status        = JobStatus.FAILED.value
    job.completed_at  = datetime.now(timezone.utc)
    job.error_message = error[:2000]
    if repo:
        repo.status        = RepoStatus.ERROR.value
        repo.error_message = error[:2000]
    db.commit()


def _update_repo_stats(db: Session, repo: Repository, repo_id: int) -> None:
    """Update file/class counts from saved metadata."""
    meta_path = repo_metadata_path(repo_id)
    if not meta_path.exists():
        return
    try:
        metadata        = json.loads(meta_path.read_text(encoding="utf-8"))
        repo.file_count = len(metadata)
        repo.class_count = sum(len(fm.get("classes", [])) for fm in metadata)
    except Exception:
        pass
