from __future__ import annotations

"""
Phase 8: Code Review Intelligence -- data models.

All findings, reports, and summary structures are Pydantic models
for type safety, serialisation, and downstream agent integration.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    """Finding severity levels, ordered from most to least critical."""
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"
    INFO     = "info"


class FindingCategory(str, Enum):
    """Code review finding categories aligned with Phase 8 requirements."""
    SOLID           = "solid"
    DESIGN_PATTERN  = "design_pattern"
    SECURITY        = "security"
    PERFORMANCE     = "performance"
    MAINTAINABILITY = "maintainability"
    DUPLICATE       = "duplicate"
    TECH_DEBT       = "tech_debt"


# Penalty weight per severity level (used for quality score calculation)
SEVERITY_WEIGHTS: Dict[str, int] = {
    Severity.CRITICAL: 10,
    Severity.HIGH:      5,
    Severity.MEDIUM:    2,
    Severity.LOW:       1,
    Severity.INFO:      0,
}


# ---------------------------------------------------------------------------
# Core finding model
# ---------------------------------------------------------------------------

class ReviewFinding(BaseModel):
    """A single code review finding with full context."""

    category:         FindingCategory
    severity:         Severity
    rule_id:          str  = Field(description="Short rule identifier, e.g. SOLID-S001")
    title:            str
    description:      str
    recommendation:   str
    affected_files:   List[str] = Field(default_factory=list)
    affected_classes: List[str] = Field(default_factory=list)
    affected_methods: List[str] = Field(default_factory=list)
    evidence:         str  = ""
    line_numbers:     List[int] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rule_id":          self.rule_id,
            "category":         self.category.value,
            "severity":         self.severity.value,
            "title":            self.title,
            "description":      self.description,
            "recommendation":   self.recommendation,
            "affected_files":   self.affected_files,
            "affected_classes": self.affected_classes,
            "affected_methods": self.affected_methods,
            "evidence":         self.evidence[:500] if self.evidence else "",
        }


# ---------------------------------------------------------------------------
# Per-category summary
# ---------------------------------------------------------------------------

class CategorySummary(BaseModel):
    """Per-category statistics aggregated from a finding list."""
    category: FindingCategory
    total:    int = 0
    critical: int = 0
    high:     int = 0
    medium:   int = 0
    low:      int = 0
    info:     int = 0


# ---------------------------------------------------------------------------
# Full review report
# ---------------------------------------------------------------------------

class CodeReviewReport(BaseModel):
    """
    Complete code review report for a repository or a filtered file set.

    quality_score: 0-100 (100 = no issues, penalised by weighted findings).
    grade: A (90+), B (75+), C (60+), D (45+), F (<45).
    """

    repository_path:    str
    reviewed_files:     int
    total_classes:      int
    total_findings:     int
    findings:           List[ReviewFinding]  = Field(default_factory=list)
    category_summaries: List[CategorySummary] = Field(default_factory=list)
    quality_score:      float = 100.0
    grade:              str   = "A"
    summary:            str   = ""
    top_issues:         List[str] = Field(default_factory=list)
    generated_at:       datetime  = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def findings_by_severity(self, severity: Severity) -> List[ReviewFinding]:
        return [f for f in self.findings if f.severity == severity]

    def findings_by_category(self, category: FindingCategory) -> List[ReviewFinding]:
        return [f for f in self.findings if f.category == category]

    # ------------------------------------------------------------------
    # Human-readable report
    # ------------------------------------------------------------------

    def to_text_report(self) -> str:
        lines = [
            "=" * 62,
            "  CODE REVIEW REPORT  --  Phase 8: Code Review Intelligence",
            "=" * 62,
            f"Repository    : {self.repository_path}",
            f"Files Reviewed: {self.reviewed_files}",
            f"Total Classes : {self.total_classes}",
            f"Total Findings: {self.total_findings}",
            f"Quality Score : {self.quality_score:.1f}/100  (Grade: {self.grade})",
            f"Generated At  : {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "EXECUTIVE SUMMARY",
            "-" * 40,
            self.summary,
            "",
        ]

        if self.top_issues:
            lines += ["TOP ISSUES", "-" * 40]
            for i, issue in enumerate(self.top_issues[:5], 1):
                lines.append(f"  {i}. {issue}")
            lines.append("")

        if self.category_summaries:
            lines += ["FINDINGS BY CATEGORY", "-" * 40]
            for cs in sorted(self.category_summaries, key=lambda x: -x.total):
                if cs.total > 0:
                    lines.append(
                        f"  {cs.category.value:<22} {cs.total:>3} total  "
                        f"(CRITICAL:{cs.critical}  HIGH:{cs.high}  "
                        f"MEDIUM:{cs.medium}  LOW:{cs.low})"
                    )
            lines.append("")

        # Group by severity for the detailed section
        by_sev: Dict[Severity, List[ReviewFinding]] = {s: [] for s in Severity}
        for f in self.findings:
            by_sev[f.severity].append(f)

        for sev in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM,
                    Severity.LOW, Severity.INFO):
            group = by_sev[sev]
            if not group:
                continue
            lines += [f"{sev.value.upper()} FINDINGS ({len(group)})", "-" * 40]
            for finding in group:
                lines += [
                    f"  [{finding.rule_id}] {finding.title}",
                    f"    Category : {finding.category.value}",
                    f"    Classes  : {', '.join(finding.affected_classes[:4])}",
                    f"    Desc     : {finding.description[:200]}",
                    f"    Fix      : {finding.recommendation[:200]}",
                ]
                if finding.evidence:
                    lines.append(f"    Evidence : {finding.evidence[:150]}")
                lines.append("")

        return "\n".join(lines)

    def to_json_report(self) -> dict:
        """Serialise to a plain dict suitable for JSON output."""
        return {
            "repository_path": self.repository_path,
            "reviewed_files":  self.reviewed_files,
            "total_classes":   self.total_classes,
            "total_findings":  self.total_findings,
            "quality_score":   round(self.quality_score, 2),
            "grade":           self.grade,
            "summary":         self.summary,
            "top_issues":      self.top_issues,
            "generated_at":    self.generated_at.isoformat(),
            "category_summaries": [
                {
                    "category": cs.category.value,
                    "total": cs.total,
                    "critical": cs.critical,
                    "high": cs.high,
                    "medium": cs.medium,
                    "low": cs.low,
                }
                for cs in self.category_summaries
            ],
            "findings": [f.to_dict() for f in self.findings],
        }
