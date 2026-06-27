from __future__ import annotations

"""
Performance analyser for Java/Spring Boot codebases.

Rules implemented:
  PERF-001  N+1 query risk: repository call inside a loop
  PERF-002  Missing @Transactional(readOnly=true) on read-only service methods
  PERF-003  Missing pagination on findAll() repository calls
  PERF-004  Eager fetch type in @OneToMany / @ManyToMany JPA relations
  PERF-005  String concatenation in loops (use StringBuilder)
  PERF-006  Missing @Cacheable on expensive/repeatable lookups
  PERF-007  Synchronised on a public method or the class level
  PERF-008  Missing @Async on methods with 'async' or 'background' in name
"""

import re
from pathlib import Path
from typing import List

from src.code_review.models import FindingCategory, ReviewFinding, Severity


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Repository/DAO call inside a loop
_LOOP_RE = re.compile(
    r'\b(?:for|while)\s*\([^{]+\)\s*\{',
    re.MULTILINE,
)
_REPO_CALL_IN_LOOP_RE = re.compile(
    r'\b(?:for|while)\b[^{]*\{[^}]*'
    r'(?:repository|repo|dao|Repo|Repository|DAO)\s*\.\s*\w+\s*\(',
    re.DOTALL,
)

# Read-only service methods that miss readOnly=true
_TRANSACTIONAL_RO_RE = re.compile(
    r'@Transactional\s*(?:\([^)]*readOnly\s*=\s*true[^)]*\))?',
    re.MULTILINE,
)
_SERVICE_READ_METHOD_RE = re.compile(
    r'(?:public|protected)\s+(?:List|Optional|Page|Set|Collection|Stream|[A-Z]\w+)'
    r'\s+(?:find|get|list|fetch|search|load|query)\w*\s*\(',
    re.MULTILINE,
)

# findAll without pagination
_FIND_ALL_RE = re.compile(r'\.\s*findAll\s*\(\s*\)', re.MULTILINE)

# Eager fetch type
_EAGER_FETCH_RE = re.compile(
    r'@(?:OneToMany|ManyToMany|ManyToOne|OneToOne)'
    r'\s*\([^)]*fetch\s*=\s*FetchType\.EAGER',
    re.MULTILINE,
)

# String concatenation in loops
_STRING_CONCAT_LOOP_RE = re.compile(
    r'(?:for|while)\b[^{]*\{[^}]*'
    r'(?:String\s+\w+|[a-z]\w*)\s*\+=\s*"',
    re.DOTALL,
)

# @Cacheable annotation
_CACHEABLE_RE = re.compile(r'@Cacheable\b', re.MULTILINE)

# Expensive/repeatable method names
_EXPENSIVE_METHOD_RE = re.compile(
    r'(?:public|protected)\s+[A-Z\w<>\[\]]+\s+'
    r'(?:calculate|compute|build|generate|process|aggregate|summarise|summarize)\w*'
    r'\s*\(',
    re.MULTILINE,
)

# Synchronised methods
_SYNCHRONIZED_METHOD_RE = re.compile(
    r'public\s+synchronized\s+\w',
    re.MULTILINE,
)

# Async method naming without @Async
_ASYNC_METHOD_NAME_RE = re.compile(
    r'(?:public|protected)\s+\w[\w<>\[\]]*\s+'
    r'(?:sendAsync|processAsync|handleAsync|\w+Async|async\w+)\s*\(',
    re.MULTILINE,
)
_ASYNC_ANNO_RE = re.compile(r'@Async\b', re.MULTILINE)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_performance(
    metadata: List[dict], repo_root: str = ""
) -> List[ReviewFinding]:
    """
    Run all performance checks against repository metadata.

    Args:
        metadata:  List of file metadata dicts from ingest.load_metadata().
        repo_root: Repository root path for resolving relative file paths.

    Returns:
        List of ReviewFinding instances for performance issues found.
    """
    findings: List[ReviewFinding] = []
    for file_meta in metadata:
        content     = _read_file(file_meta.get("file_path", ""), repo_root)
        classes     = file_meta.get("classes", [])
        annotations = file_meta.get("annotations", [])
        file_name   = Path(file_meta.get("file_path", "unknown")).name

        if not content:
            continue

        for cls in classes:
            findings += _check_n_plus_one(cls, content, file_name)
            findings += _check_transactional_readonly(cls, content, annotations, file_name)
            findings += _check_find_all_pagination(cls, content, file_name)
            findings += _check_eager_fetch(cls, content, file_name)
            findings += _check_string_concat_loop(cls, content, file_name)
            findings += _check_missing_cacheable(cls, content, annotations, file_name)
            findings += _check_synchronized_methods(cls, content, file_name)
            findings += _check_missing_async(cls, content, file_name)

    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_file(file_path: str, repo_root: str) -> str:
    try:
        p = Path(file_path)
        if not p.is_absolute() and repo_root:
            p = Path(repo_root) / p
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_n_plus_one(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not _REPO_CALL_IN_LOOP_RE.search(content):
        return []
    return [ReviewFinding(
        category=FindingCategory.PERFORMANCE,
        severity=Severity.HIGH,
        rule_id="PERF-001",
        title=f"N+1 query risk in {class_name}",
        description=(
            f"{class_name} appears to call a repository or DAO method inside a loop. "
            "This is the classic N+1 query pattern and can cause severe performance "
            "degradation as the dataset grows."
        ),
        recommendation=(
            "Batch the repository call outside the loop: fetch all required entities "
            "in one query, then process them in memory. "
            "Consider using Spring Data's JPA JOIN FETCH, @EntityGraph, "
            "or a custom @Query with IN clause."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _check_transactional_readonly(
    class_name: str, content: str, annotations: List[str], file_name: str
) -> List[ReviewFinding]:
    # Only flag @Service or @Component classes
    is_service = any(a in ("Service", "Component") for a in annotations)
    if not is_service:
        return []

    read_methods = _SERVICE_READ_METHOD_RE.findall(content)
    if not read_methods:
        return []

    # Check if readOnly=true is used anywhere in the class
    has_readonly = bool(re.search(r'readOnly\s*=\s*true', content))
    transactional_count = len(re.findall(r'@Transactional\b', content))

    if read_methods and transactional_count == 0 and not has_readonly:
        return [ReviewFinding(
            category=FindingCategory.PERFORMANCE,
            severity=Severity.LOW,
            rule_id="PERF-002",
            title=f"Missing @Transactional(readOnly=true) on read methods in {class_name}",
            description=(
                f"{class_name} has {len(read_methods)} read-only method(s) "
                "(find/get/list/fetch) but no @Transactional(readOnly=true). "
                "Setting readOnly=true enables JPA flush-mode optimisations "
                "and database-level read optimisations."
            ),
            recommendation=(
                "Annotate read-only service methods with "
                "@Transactional(readOnly = true) to allow the JPA provider "
                "to skip dirty checking and enable read-only connection hints."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []


def _check_find_all_pagination(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    find_all_hits = _FIND_ALL_RE.findall(content)
    if not find_all_hits:
        return []
    has_pageable = bool(re.search(r'Pageable|PageRequest|Page<', content))
    if has_pageable:
        return []  # Pagination is already used somewhere in the class
    return [ReviewFinding(
        category=FindingCategory.PERFORMANCE,
        severity=Severity.MEDIUM,
        rule_id="PERF-003",
        title=f"Unbounded findAll() in {class_name}",
        description=(
            f"{class_name} calls findAll() without pagination "
            f"({len(find_all_hits)} occurrence(s)). Loading the full table into "
            "memory is dangerous for large datasets and can cause OutOfMemoryError."
        ),
        recommendation=(
            "Add a Pageable parameter to repository methods and return Page<T>. "
            "Accept page/size parameters from the API layer or apply a sensible default "
            "maximum (e.g. PageRequest.of(0, 200))."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _check_eager_fetch(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    eager_hits = _EAGER_FETCH_RE.findall(content)
    if not eager_hits:
        return []
    return [ReviewFinding(
        category=FindingCategory.PERFORMANCE,
        severity=Severity.MEDIUM,
        rule_id="PERF-004",
        title=f"EAGER fetch type in {class_name} ({len(eager_hits)} relation(s))",
        description=(
            f"{class_name} uses FetchType.EAGER on {len(eager_hits)} "
            "@OneToMany/@ManyToMany relation(s). Eager fetching loads all related "
            "entities regardless of whether they are needed, increasing query cost."
        ),
        recommendation=(
            "Use FetchType.LAZY (the default for @OneToMany/@ManyToMany) and "
            "load associations explicitly via JOIN FETCH in JPQL or @EntityGraph "
            "only when needed."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _check_string_concat_loop(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not _STRING_CONCAT_LOOP_RE.search(content):
        return []
    return [ReviewFinding(
        category=FindingCategory.PERFORMANCE,
        severity=Severity.LOW,
        rule_id="PERF-005",
        title=f"String concatenation in loop in {class_name}",
        description=(
            f"{class_name} appears to concatenate strings using += inside a loop. "
            "Each concatenation allocates a new String object, causing O(n²) "
            "memory and CPU overhead."
        ),
        recommendation=(
            "Use StringBuilder.append() inside loops, then call toString() once "
            "after the loop. For simple joins, consider String.join() or "
            "Collectors.joining() in a stream."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _check_missing_cacheable(
    class_name: str, content: str, annotations: List[str], file_name: str
) -> List[ReviewFinding]:
    is_service = any(a in ("Service", "Component") for a in annotations)
    if not is_service:
        return []
    expensive_methods = _EXPENSIVE_METHOD_RE.findall(content)
    if not expensive_methods:
        return []
    if _CACHEABLE_RE.search(content):
        return []  # @Cacheable already present
    return [ReviewFinding(
        category=FindingCategory.PERFORMANCE,
        severity=Severity.INFO,
        rule_id="PERF-006",
        title=f"Consider @Cacheable on expensive methods in {class_name}",
        description=(
            f"{class_name} has {len(expensive_methods)} method(s) with names "
            "suggesting expensive computation (calculate/compute/build/generate/process) "
            "but no @Cacheable annotation."
        ),
        recommendation=(
            "If these methods produce deterministic results for the same input, "
            "add @Cacheable(value = \"cacheName\") and configure a cache manager "
            "(Caffeine, Redis, etc.) to avoid repeated computation."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _check_synchronized_methods(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    hits = _SYNCHRONIZED_METHOD_RE.findall(content)
    if not hits:
        return []
    return [ReviewFinding(
        category=FindingCategory.PERFORMANCE,
        severity=Severity.MEDIUM,
        rule_id="PERF-007",
        title=f"Coarse-grained synchronization in {class_name}",
        description=(
            f"{class_name} has {len(hits)} public synchronized method(s). "
            "Method-level synchronization serialises all callers and can "
            "become a severe bottleneck under concurrent load."
        ),
        recommendation=(
            "Replace method-level synchronized with fine-grained locks: "
            "ReentrantLock, ReadWriteLock, or java.util.concurrent data structures. "
            "For Spring beans, prefer stateless design to avoid synchronization "
            "entirely."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _check_missing_async(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    async_methods = _ASYNC_METHOD_NAME_RE.findall(content)
    if not async_methods:
        return []
    if _ASYNC_ANNO_RE.search(content):
        return []
    return [ReviewFinding(
        category=FindingCategory.PERFORMANCE,
        severity=Severity.LOW,
        rule_id="PERF-008",
        title=f"Async-named methods lack @Async in {class_name}",
        description=(
            f"{class_name} has method(s) with names suggesting async execution "
            "but no @Async annotation. These methods run synchronously on the "
            "caller's thread, blocking the request."
        ),
        recommendation=(
            "Annotate methods that should run asynchronously with @Async and "
            "return CompletableFuture<T> or void. Enable async support with "
            "@EnableAsync on a configuration class."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]
