from __future__ import annotations

"""
Phase 8: Code Review Engine.

Orchestrates all static analysers and (optionally) an LLM-powered deep review
pass to produce a comprehensive CodeReviewReport.

Usage:
    from src.code_review.engine import CodeReviewEngine

    engine = CodeReviewEngine(repo_root="/path/to/repo")
    report = engine.run(metadata)            # full static analysis
    report = engine.run(metadata, llm=llm)   # static + LLM deep-dive
"""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.code_review.models import (
    CategorySummary,
    CodeReviewReport,
    FindingCategory,
    ReviewFinding,
    Severity,
    SEVERITY_WEIGHTS,
)
from src.code_review.analyzers import (
    analyze_solid,
    analyze_security,
    analyze_performance,
    analyze_maintainability,
    analyze_duplicates,
    analyze_tech_debt,
    analyze_patterns,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Score / grade helpers
# ---------------------------------------------------------------------------

_GRADE_THRESHOLDS = [(90, "A"), (75, "B"), (60, "C"), (45, "D")]


def _compute_score(findings: List[ReviewFinding], total_classes: int) -> float:
    """
    Compute a 0-100 quality score.

    Penalty is scaled by class count so large repos don't unfairly bottom out.
    Score = max(0, 100 - total_penalty / class_scale)
    """
    if total_classes == 0:
        return 100.0

    penalty = sum(SEVERITY_WEIGHTS.get(f.severity, 0) for f in findings)
    # Scale: 1 critical per 10 classes drops score by ~10 points
    class_scale = max(total_classes / 10, 1)
    score = max(0.0, 100.0 - penalty / class_scale)
    return round(score, 2)


def _grade(score: float) -> str:
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def _build_category_summaries(
    findings: List[ReviewFinding],
) -> List[CategorySummary]:
    agg: Dict[FindingCategory, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for f in findings:
        agg[f.category]["total"] += 1
        agg[f.category][f.severity.value] += 1

    summaries = []
    for cat, counts in sorted(agg.items(), key=lambda x: -x[1]["total"]):
        summaries.append(CategorySummary(
            category=cat,
            total=counts["total"],
            critical=counts.get("critical", 0),
            high=counts.get("high", 0),
            medium=counts.get("medium", 0),
            low=counts.get("low", 0),
            info=counts.get("info", 0),
        ))
    return summaries


def _top_issues(findings: List[ReviewFinding], n: int = 5) -> List[str]:
    """Return the n highest-severity finding titles."""
    ordered = sorted(
        findings,
        key=lambda f: list(Severity).index(f.severity),
    )
    seen: set = set()
    result = []
    for f in ordered:
        key = f.rule_id + "|" + f.title[:60]
        if key not in seen:
            seen.add(key)
            result.append(f"[{f.severity.value.upper()}] [{f.rule_id}] {f.title}")
        if len(result) >= n:
            break
    return result


def _executive_summary(
    findings: List[ReviewFinding],
    reviewed_files: int,
    score: float,
    grade: str,
) -> str:
    counts = defaultdict(int)
    for f in findings:
        counts[f.severity.value] += 1

    critical = counts.get("critical", 0)
    high     = counts.get("high", 0)
    medium   = counts.get("medium", 0)
    low      = counts.get("low", 0)

    lines = [
        f"Reviewed {reviewed_files} Java source file(s). "
        f"Overall quality score: {score:.1f}/100 (Grade: {grade}).",
        "",
        f"Findings: {critical} CRITICAL, {high} HIGH, {medium} MEDIUM, {low} LOW.",
    ]

    if critical > 0:
        lines.append(
            f"CRITICAL attention required: {critical} critical finding(s) "
            "including potential security vulnerabilities or severe SOLID violations."
        )
    if high > 0:
        lines.append(
            f"HIGH priority: {high} finding(s) should be addressed before the next release."
        )

    top_cats = sorted(
        _build_category_summaries(findings),
        key=lambda cs: -(cs.critical * 10 + cs.high * 5 + cs.medium * 2),
    )[:3]
    if top_cats:
        cat_names = [c.category.value.replace("_", " ") for c in top_cats if c.total > 0]
        lines.append(
            f"Top concern areas: {', '.join(cat_names)}."
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CodeReviewEngine:
    """
    Orchestrates all Phase 8 code review analysers.

    Args:
        repo_root:         Absolute path to the repository root.
                           Used to resolve relative file paths in metadata.
        enabled_analyzers: Optional list of analyzer names to enable.
                           Defaults to all. Options: solid, security, performance,
                           maintainability, duplicates, tech_debt, patterns.
    """

    _ALL_ANALYZERS = (
        "solid",
        "security",
        "performance",
        "maintainability",
        "duplicates",
        "tech_debt",
        "patterns",
    )

    def __init__(
        self,
        repo_root: str = "",
        enabled_analyzers: Optional[List[str]] = None,
    ) -> None:
        self.repo_root         = repo_root
        self.enabled_analyzers = set(
            enabled_analyzers if enabled_analyzers is not None else self._ALL_ANALYZERS
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        metadata: List[dict],
        llm: Any = None,
        target_classes: Optional[List[str]] = None,
    ) -> CodeReviewReport:
        """
        Run the full code review pipeline.

        Args:
            metadata:        List of file metadata dicts (from ingest.load_metadata()).
            llm:             Optional LLM for the deep-review pass (not required).
            target_classes:  If provided, only review these classes (for focused review).

        Returns:
            CodeReviewReport with all findings, scores, and summaries.
        """
        if target_classes:
            metadata = [
                fm for fm in metadata
                if any(c in target_classes for c in fm.get("classes", []))
            ]

        all_findings: List[ReviewFinding] = []
        total_classes = sum(len(fm.get("classes", [])) for fm in metadata)
        reviewed_files = len(metadata)

        logger.info(
            "Code review starting: %d files, %d classes",
            reviewed_files, total_classes,
        )

        if "solid" in self.enabled_analyzers:
            logger.debug("Running SOLID analyser...")
            all_findings += analyze_solid(metadata, self.repo_root)

        if "security" in self.enabled_analyzers:
            logger.debug("Running security analyser...")
            all_findings += analyze_security(metadata, self.repo_root)

        if "performance" in self.enabled_analyzers:
            logger.debug("Running performance analyser...")
            all_findings += analyze_performance(metadata, self.repo_root)

        if "maintainability" in self.enabled_analyzers:
            logger.debug("Running maintainability analyser...")
            all_findings += analyze_maintainability(metadata, self.repo_root)

        if "duplicates" in self.enabled_analyzers:
            logger.debug("Running duplicate code detector...")
            all_findings += analyze_duplicates(metadata, self.repo_root)

        if "tech_debt" in self.enabled_analyzers:
            logger.debug("Running tech debt analyser...")
            all_findings += analyze_tech_debt(metadata, self.repo_root)

        if "patterns" in self.enabled_analyzers:
            logger.debug("Running design pattern detector...")
            all_findings += analyze_patterns(metadata, self.repo_root)

        # LLM-powered deep review for top-severity findings
        if llm is not None:
            all_findings += self._llm_review(llm, metadata, all_findings)

        # Dedup: remove exact-duplicate rule_id+class combinations
        all_findings = _deduplicate(all_findings)

        score      = _compute_score(all_findings, total_classes)
        grade      = _grade(score)
        summaries  = _build_category_summaries(all_findings)
        top_issues = _top_issues(all_findings)
        summary    = _executive_summary(all_findings, reviewed_files, score, grade)

        logger.info(
            "Code review complete: %d findings, score=%.1f, grade=%s",
            len(all_findings), score, grade,
        )

        return CodeReviewReport(
            repository_path=self.repo_root or ".",
            reviewed_files=reviewed_files,
            total_classes=total_classes,
            total_findings=len(all_findings),
            findings=all_findings,
            category_summaries=summaries,
            quality_score=score,
            grade=grade,
            summary=summary,
            top_issues=top_issues,
        )

    def run_for_class(
        self,
        class_name: str,
        metadata: List[dict],
        llm: Any = None,
    ) -> CodeReviewReport:
        """Convenience method to review a single class."""
        return self.run(metadata, llm=llm, target_classes=[class_name])

    # ------------------------------------------------------------------
    # LLM deep-review pass
    # ------------------------------------------------------------------

    def _llm_review(
        self,
        llm: Any,
        metadata: List[dict],
        existing_findings: List[ReviewFinding],
    ) -> List[ReviewFinding]:
        """
        Use the LLM to review the top 3 CRITICAL/HIGH findings in depth and
        generate additional nuanced findings that static analysis may miss.
        """
        from src.code_review.prompts import build_llm_review_prompt, parse_llm_findings

        high_priority = [
            f for f in existing_findings
            if f.severity in (Severity.CRITICAL, Severity.HIGH)
        ][:5]

        if not high_priority:
            return []

        # Build a small context: file snippets for affected classes
        class_snippets: Dict[str, str] = {}
        for finding in high_priority:
            for cls in finding.affected_classes[:2]:
                if cls in class_snippets:
                    continue
                for fm in metadata:
                    if cls in fm.get("classes", []):
                        content = _read_file_safe(
                            fm.get("file_path", ""), self.repo_root
                        )
                        if content:
                            class_snippets[cls] = content[:3000]
                        break

        if not class_snippets:
            return []

        prompt = build_llm_review_prompt(high_priority, class_snippets)
        try:
            response = llm.invoke(prompt)
            raw_text = getattr(response, "content", str(response))
            return parse_llm_findings(raw_text)
        except Exception as exc:
            logger.warning("LLM review pass failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def save_report(self, report: CodeReviewReport, output_path: str) -> None:
        """Save a JSON report to disk."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.to_json_report(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Report saved to %s", path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _deduplicate(findings: List[ReviewFinding]) -> List[ReviewFinding]:
    seen: set = set()
    result = []
    for f in findings:
        key = (f.rule_id, frozenset(f.affected_classes))
        if key not in seen:
            seen.add(key)
            result.append(f)
    return result


def _read_file_safe(file_path: str, repo_root: str) -> str:
    try:
        p = Path(file_path)
        if not p.is_absolute() and repo_root:
            p = Path(repo_root) / p
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return ""
