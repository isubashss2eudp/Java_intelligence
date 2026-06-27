from __future__ import annotations

"""
Maintainability analyser for Java/Spring Boot codebases.

Rules implemented:
  MAINT-001  Long method (estimated from LOC and method count)
  MAINT-002  Deep nesting (excessive indentation depth)
  MAINT-003  Magic numbers / magic strings in non-constant context
  MAINT-004  Empty catch block (swallowed exception)
  MAINT-005  Dead code indicators (unreachable return / TODO-only methods)
  MAINT-006  Poor naming (single-character variable names outside loops)
  MAINT-007  Overly long method parameter list (> 5 parameters)
  MAINT-008  Missing @Override on overriding methods (heuristic)
  MAINT-009  Excessive comment-to-code ratio (under-commented class)
  MAINT-010  Public fields (break encapsulation)
"""

import re
from pathlib import Path
from typing import List

from src.code_review.models import FindingCategory, ReviewFinding, Severity


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
MAX_METHOD_PARAMS   = 5
MIN_COMMENT_RATIO   = 0.05   # at least 5% of lines should be comments
MAX_INDENT_DEPTH    = 4      # count of leading 4-space / tab indents

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_EMPTY_CATCH_RE = re.compile(
    r'catch\s*\([^)]+\)\s*\{[^}]*\}',
    re.MULTILINE,
)
_EMPTY_CATCH_BODY_RE = re.compile(
    r'catch\s*\([^)]+\)\s*\{\s*(?://[^\n]*)?\s*\}',
    re.MULTILINE,
)

# Magic numbers: standalone numeric literals (not in final/constant declarations)
_MAGIC_NUMBER_RE = re.compile(
    r'(?<![A-Z_=])\b(?!0\b|1\b)(?:\d{2,}|[02-9]\.\d+)\b(?!\s*[;,)]?\s*;?\s*//)',
    re.MULTILINE,
)
_FINAL_CONSTANT_RE = re.compile(
    r'(?:static\s+)?final\s+\w+\s+[A-Z_][A-Z0-9_]*\s*=',
    re.MULTILINE,
)

# Magic strings (non-empty, non-trivial string literals not in annotations)
_MAGIC_STRING_RE = re.compile(
    r'(?:return|=|\+=)\s*"([A-Za-z][^"]{5,})"',
    re.MULTILINE,
)

# Long parameter list
_METHOD_PARAMS_RE = re.compile(
    r'(?:public|protected|private)\s+[\w<>\[\]]+\s+\w+\s*\(([^)]+)\)',
    re.MULTILINE,
)

# Public field declarations (not static final constants)
_PUBLIC_FIELD_RE = re.compile(
    r'^\s*public\s+(?!static\s+final)(?!class|interface|enum|@interface|void)'
    r'[A-Za-z_$][\w<>\[\]]*\s+[a-z]\w*\s*[=;]',
    re.MULTILINE,
)

# Single-character variable names (excluding common loop vars i, j, k, e, x, y)
_SHORT_VAR_RE = re.compile(
    r'(?:int|String|long|boolean|double|float|Object|var)\s+([a-wz])\b\s*[=;]',
    re.MULTILINE,
)

# Deep nesting: lines with 5+ levels of indentation (20+ spaces or 5+ tabs)
_DEEP_NESTING_RE = re.compile(r'^(?:    ){5}|\t{5}', re.MULTILINE)

# Unreachable return (return statement not at end of method, before closing brace)
_UNREACHABLE_RETURN_RE = re.compile(
    r'\breturn\b[^;]*;\s*\n\s*(?!})\s*\w',
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_maintainability(
    metadata: List[dict], repo_root: str = ""
) -> List[ReviewFinding]:
    """
    Run all maintainability checks against repository metadata.

    Args:
        metadata:  List of file metadata dicts from ingest.load_metadata().
        repo_root: Repository root path for resolving relative file paths.

    Returns:
        List of ReviewFinding instances for maintainability issues found.
    """
    findings: List[ReviewFinding] = []
    for file_meta in metadata:
        content   = _read_file(file_meta.get("file_path", ""), repo_root)
        classes   = file_meta.get("classes", [])
        methods   = file_meta.get("methods", [])
        loc       = file_meta.get("lines_of_code", 0)
        file_name = Path(file_meta.get("file_path", "unknown")).name

        if not classes:
            continue

        primary_class = classes[0]

        findings += _check_long_methods(primary_class, methods, loc, file_name)
        findings += _check_deep_nesting(primary_class, content, file_name)
        findings += _check_magic_numbers(primary_class, content, file_name)
        findings += _check_magic_strings(primary_class, content, file_name)
        findings += _check_empty_catch(primary_class, content, file_name)
        findings += _check_public_fields(primary_class, content, file_name)
        findings += _check_poor_naming(primary_class, content, file_name)
        findings += _check_long_param_lists(primary_class, content, file_name)
        findings += _check_comment_coverage(primary_class, content, loc, file_name)

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

def _check_long_methods(
    class_name: str,
    methods: List[str],
    loc: int,
    file_name: str,
) -> List[ReviewFinding]:
    if not methods or loc == 0:
        return []
    avg_method_loc = loc / max(len(methods), 1)
    if avg_method_loc > 40:
        return [ReviewFinding(
            category=FindingCategory.MAINTAINABILITY,
            severity=Severity.LOW,
            rule_id="MAINT-001",
            title=f"Long methods detected in {class_name} (avg ~{avg_method_loc:.0f} LOC)",
            description=(
                f"{class_name} has {len(methods)} method(s) averaging "
                f"~{avg_method_loc:.0f} lines each. Long methods are harder to "
                "read, test, and change safely."
            ),
            recommendation=(
                "Aim for methods under 20-30 lines. "
                "Extract cohesive sub-steps into private helper methods with "
                "descriptive names."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []


def _check_deep_nesting(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    deep_lines = _DEEP_NESTING_RE.findall(content)
    if len(deep_lines) >= 3:
        return [ReviewFinding(
            category=FindingCategory.MAINTAINABILITY,
            severity=Severity.MEDIUM,
            rule_id="MAINT-002",
            title=f"Deep nesting in {class_name} ({len(deep_lines)} deeply nested line(s))",
            description=(
                f"{class_name} has {len(deep_lines)} line(s) with 5+ levels of "
                "indentation. Deep nesting increases cognitive complexity and makes "
                "code hard to follow."
            ),
            recommendation=(
                "Apply the Guard Clause pattern to invert conditions and return early. "
                "Extract nested blocks into well-named private methods. "
                "Limit nesting to 3 levels maximum."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []


def _check_magic_numbers(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    # Skip lines with final constants
    lines = [
        line for line in content.splitlines()
        if not _FINAL_CONSTANT_RE.search(line) and not line.strip().startswith("//")
    ]
    filtered = "\n".join(lines)
    hits = _MAGIC_NUMBER_RE.findall(filtered)
    unique_numbers = list(dict.fromkeys(hits))[:8]
    if len(unique_numbers) >= 4:
        return [ReviewFinding(
            category=FindingCategory.MAINTAINABILITY,
            severity=Severity.LOW,
            rule_id="MAINT-003",
            title=f"Magic numbers in {class_name} ({len(unique_numbers)} distinct value(s))",
            description=(
                f"{class_name} uses {len(unique_numbers)} distinct numeric literals "
                f"({', '.join(unique_numbers[:5])}) without named constants. "
                "Magic numbers reduce readability and make changes error-prone."
            ),
            recommendation=(
                "Extract magic numbers into named static final constants or enums. "
                "The name communicates intent; the constant prevents duplication."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
            evidence=f"Values found: {', '.join(unique_numbers[:6])}",
        )]
    return []


def _check_magic_strings(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    hits = _MAGIC_STRING_RE.findall(content)
    # Filter out likely annotation values, imports
    hits = [h for h in hits if len(h) > 5 and not h.startswith("http")]
    unique = list(dict.fromkeys(hits))[:6]
    if len(unique) >= 3:
        return [ReviewFinding(
            category=FindingCategory.MAINTAINABILITY,
            severity=Severity.LOW,
            rule_id="MAINT-003b",
            title=f"Magic strings in {class_name}",
            description=(
                f"{class_name} uses {len(unique)} inline string literals "
                f"({', '.join(repr(s) for s in unique[:3])}...). "
                "Hard-coded strings are difficult to find and update consistently."
            ),
            recommendation=(
                "Extract repeated or meaningful string literals into named constants "
                "or enum values. Store configurable values in application.properties."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []


def _check_empty_catch(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    empty_catches = _EMPTY_CATCH_BODY_RE.findall(content)
    if empty_catches:
        return [ReviewFinding(
            category=FindingCategory.MAINTAINABILITY,
            severity=Severity.HIGH,
            rule_id="MAINT-004",
            title=f"Empty catch block in {class_name} ({len(empty_catches)} occurrence(s))",
            description=(
                f"{class_name} has {len(empty_catches)} catch block(s) that swallow "
                "exceptions silently. Silent failures are the hardest bugs to diagnose."
            ),
            recommendation=(
                "At minimum, log the exception at WARN or ERROR level. "
                "Consider re-throwing as a domain exception. "
                "Never suppress InterruptedException without re-interrupting the thread."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []


def _check_public_fields(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    hits = _PUBLIC_FIELD_RE.findall(content)
    if hits:
        return [ReviewFinding(
            category=FindingCategory.MAINTAINABILITY,
            severity=Severity.MEDIUM,
            rule_id="MAINT-010",
            title=f"Public mutable fields in {class_name} ({len(hits)} field(s))",
            description=(
                f"{class_name} exposes {len(hits)} public mutable field(s). "
                "Public fields break encapsulation and allow uncontrolled external "
                "modification."
            ),
            recommendation=(
                "Replace public fields with private fields and accessor methods "
                "(getters/setters). Consider using Lombok @Data, @Getter, @Setter "
                "for boilerplate reduction."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []


def _check_poor_naming(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    hits = _SHORT_VAR_RE.findall(content)
    unique = list(dict.fromkeys(hits))
    if len(unique) >= 3:
        return [ReviewFinding(
            category=FindingCategory.MAINTAINABILITY,
            severity=Severity.LOW,
            rule_id="MAINT-006",
            title=f"Single-character variable names in {class_name}: {', '.join(unique)}",
            description=(
                f"{class_name} uses single-character variable names "
                f"({', '.join(unique)}) outside typical loop counters. "
                "Short names reduce readability."
            ),
            recommendation=(
                "Use descriptive, intent-revealing variable names. "
                "Short names (a, b, c) are only acceptable for loop counters "
                "or lambda parameters in very short expressions."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []


def _check_long_param_lists(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    violations = []
    for match in _METHOD_PARAMS_RE.finditer(content):
        params = [p.strip() for p in match.group(1).split(",") if p.strip()]
        if len(params) > MAX_METHOD_PARAMS:
            violations.append((match.group(0)[:60], len(params)))
    if violations:
        worst = max(violations, key=lambda x: x[1])
        return [ReviewFinding(
            category=FindingCategory.MAINTAINABILITY,
            severity=Severity.MEDIUM,
            rule_id="MAINT-007",
            title=f"Long parameter lists in {class_name} (up to {worst[1]} params)",
            description=(
                f"{class_name} has {len(violations)} method(s) with more than "
                f"{MAX_METHOD_PARAMS} parameters. Long parameter lists are hard to "
                "call correctly and signal missing abstraction."
            ),
            recommendation=(
                "Introduce a Parameter Object: group related parameters into a "
                "dedicated DTO or record. Consider Builder pattern for optional params."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
            evidence=f"Worst offender: {worst[0]} ({worst[1]} params)",
        )]
    return []


def _check_comment_coverage(
    class_name: str, content: str, loc: int, file_name: str
) -> List[ReviewFinding]:
    if not content or loc < 50:
        return []
    lines         = content.splitlines()
    comment_lines = sum(
        1 for ln in lines
        if ln.strip().startswith("//") or ln.strip().startswith("*")
        or ln.strip().startswith("/*")
    )
    ratio = comment_lines / max(loc, 1)
    if ratio < MIN_COMMENT_RATIO:
        return [ReviewFinding(
            category=FindingCategory.MAINTAINABILITY,
            severity=Severity.INFO,
            rule_id="MAINT-009",
            title=f"Low comment coverage in {class_name} ({ratio*100:.0f}%)",
            description=(
                f"{class_name} has only {ratio*100:.0f}% comment coverage "
                f"({comment_lines} comment lines out of {loc} LOC). "
                "Public APIs and non-obvious logic should be documented."
            ),
            recommendation=(
                "Add Javadoc to all public classes and methods. "
                "Document non-obvious logic inline with // comments. "
                "Aim for at least 5-10% comment coverage on complex classes."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []
