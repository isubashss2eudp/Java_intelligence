from __future__ import annotations

"""
Phase 8: Code Review Intelligence.

Provides static and LLM-powered code review for Java/Spring Boot repositories.

Capabilities:
  - SOLID principles analysis (SRP, OCP, LSP, ISP, DIP)
  - Design pattern detection (Singleton, Factory, Builder, Observer, Strategy)
  - Anti-pattern detection (God Class, Service Locator, Anemic Model)
  - Security vulnerability analysis (OWASP Top 10 aligned)
  - Performance analysis (N+1 queries, eager fetch, unbounded findAll, etc.)
  - Maintainability analysis (deep nesting, magic numbers, empty catch, etc.)
  - Duplicate code detection (structural clone, method signature duplication)
  - Technical debt detection (TODO/FIXME, missing tests, hardcoded values)

Quick start:
    from src.code_review import CodeReviewEngine
    from src.ingest import load_metadata

    engine = CodeReviewEngine(repo_root="/path/to/repo")
    report = engine.run(load_metadata())
    print(report.to_text_report())
    print(report.quality_score)
"""

from src.code_review.engine import CodeReviewEngine
from src.code_review.models import (
    CodeReviewReport,
    ReviewFinding,
    FindingCategory,
    Severity,
    CategorySummary,
)

__all__ = [
    "CodeReviewEngine",
    "CodeReviewReport",
    "ReviewFinding",
    "FindingCategory",
    "Severity",
    "CategorySummary",
]
