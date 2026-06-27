from __future__ import annotations

"""
Duplicate code detector for Java/Spring Boot codebases.

Detection strategy:
  1. Method-signature similarity -- identical or near-identical public method
     signatures across different classes (same name, arity, return type prefix).
  2. Class-level structural clones -- classes with very similar sets of methods
     (Jaccard similarity >= threshold).
  3. Repeated import block similarity -- classes that share almost all imports
     may be candidates for consolidation.

Rules:
  DUP-001  Duplicate / very similar method signature in multiple classes
  DUP-002  Structurally similar classes (potential code clone)
  DUP-003  Near-identical import sets (possible utility duplication)
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

from src.code_review.models import FindingCategory, ReviewFinding, Severity


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
CLASS_JACCARD_THRESHOLD  = 0.70   # method-set similarity to flag structural clone
IMPORT_JACCARD_THRESHOLD = 0.85   # import-set similarity
MIN_METHODS_FOR_CLONE    = 5      # don't flag tiny classes


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_METHOD_SIG_RE = re.compile(
    r'(?:public|protected)\s+'
    r'(?:static\s+)?'
    r'(?:final\s+)?'
    r'([\w<>\[\]]+)\s+'        # return type (group 1)
    r'(\w+)\s*'                # method name (group 2)
    r'\(([^)]*)\)',            # parameters (group 3)
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_duplicates(
    metadata: List[dict], repo_root: str = ""
) -> List[ReviewFinding]:
    """
    Detect duplicate and near-duplicate code across the repository.

    Args:
        metadata:  List of file metadata dicts from ingest.load_metadata().
        repo_root: Repository root path for resolving relative file paths.

    Returns:
        List of ReviewFinding instances for duplicate code detected.
    """
    findings: List[ReviewFinding] = []

    # Build a per-class view: {class_name: {methods, imports, file_name}}
    class_info: Dict[str, dict] = {}
    for file_meta in metadata:
        content   = _read_file(file_meta.get("file_path", ""), repo_root)
        classes   = file_meta.get("classes", [])
        imports   = set(file_meta.get("imports", []))
        file_name = Path(file_meta.get("file_path", "unknown")).name

        for cls in classes:
            method_sigs = _extract_method_signatures(content) if content else []
            class_info[cls] = {
                "methods":   set(method_sigs),
                "imports":   imports,
                "file_name": file_name,
                "raw_methods": file_meta.get("methods", []),
            }

    # DUP-001: identical method signatures in multiple classes
    findings += _check_method_signature_duplicates(class_info)

    # DUP-002: structurally similar classes
    findings += _check_structural_clones(class_info)

    # DUP-003: near-identical import sets
    findings += _check_import_similarity(class_info)

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


def _extract_method_signatures(content: str) -> List[str]:
    """Extract canonical method signatures: 'returnType methodName(paramCount)'."""
    sigs = []
    for m in _METHOD_SIG_RE.finditer(content):
        ret_type   = m.group(1).split("<")[0]  # strip generics from return type
        name       = m.group(2)
        param_count = len([p for p in m.group(3).split(",") if p.strip()])
        sigs.append(f"{ret_type} {name}({param_count})")
    return sigs


def _jaccard(a: Set, b: Set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# DUP-001: Method signature duplicates
# ---------------------------------------------------------------------------

def _check_method_signature_duplicates(
    class_info: Dict[str, dict]
) -> List[ReviewFinding]:
    findings: List[ReviewFinding] = []

    # Map signature -> [class_names]
    sig_to_classes: Dict[str, List[str]] = defaultdict(list)
    for cls, info in class_info.items():
        for sig in info["methods"]:
            sig_to_classes[sig].append(cls)

    # Find signatures shared by 3+ classes (2 is common interface impl)
    flagged: Dict[str, List[str]] = {
        sig: classes
        for sig, classes in sig_to_classes.items()
        if len(classes) >= 3
    }

    if not flagged:
        return findings

    # Group into clusters of related duplicates
    reported_classes: Set[str] = set()
    for sig, classes in sorted(flagged.items(), key=lambda x: -len(x[1]))[:10]:
        key = tuple(sorted(classes))
        if key in reported_classes:
            continue
        # Only flag if classes are not in an obvious interface hierarchy
        files = list({class_info[c]["file_name"] for c in classes})
        findings.append(ReviewFinding(
            category=FindingCategory.DUPLICATE,
            severity=Severity.LOW,
            rule_id="DUP-001",
            title=f"Duplicate method signature '{sig}' in {len(classes)} classes",
            description=(
                f"Method signature '{sig}' appears in {len(classes)} classes: "
                f"{', '.join(classes[:5])}. "
                "This may indicate copy-paste reuse or a missing shared abstraction."
            ),
            recommendation=(
                "Extract the shared method into a common base class, utility class, "
                "or interface default method. Centralise the implementation to "
                "eliminate duplication and ensure consistent behaviour."
            ),
            affected_files=files[:6],
            affected_classes=classes[:6],
            evidence=f"Shared signature: {sig}",
        ))
        reported_classes.add(key)

    return findings


# ---------------------------------------------------------------------------
# DUP-002: Structural clones
# ---------------------------------------------------------------------------

def _check_structural_clones(
    class_info: Dict[str, dict]
) -> List[ReviewFinding]:
    findings: List[ReviewFinding] = []
    classes = [
        (name, info)
        for name, info in class_info.items()
        if len(info["methods"]) >= MIN_METHODS_FOR_CLONE
    ]

    reported: Set[Tuple[str, str]] = set()
    for i in range(len(classes)):
        for j in range(i + 1, len(classes)):
            name_a, info_a = classes[i]
            name_b, info_b = classes[j]
            sim = _jaccard(info_a["methods"], info_b["methods"])
            if sim >= CLASS_JACCARD_THRESHOLD:
                pair = tuple(sorted([name_a, name_b]))
                if pair in reported:
                    continue
                reported.add(pair)
                shared = info_a["methods"] & info_b["methods"]
                findings.append(ReviewFinding(
                    category=FindingCategory.DUPLICATE,
                    severity=Severity.MEDIUM,
                    rule_id="DUP-002",
                    title=(
                        f"Structural clone: {name_a} and {name_b} "
                        f"({sim*100:.0f}% similar)"
                    ),
                    description=(
                        f"{name_a} and {name_b} share {len(shared)} out of "
                        f"{len(info_a['methods'] | info_b['methods'])} method signatures "
                        f"(Jaccard similarity: {sim*100:.0f}%). "
                        "These classes may be code clones or candidates for consolidation."
                    ),
                    recommendation=(
                        "Consider merging into a single generic class, introducing "
                        "a common abstract base class, or extracting shared logic "
                        "into a utility/helper class."
                    ),
                    affected_files=[
                        info_a["file_name"],
                        info_b["file_name"],
                    ],
                    affected_classes=[name_a, name_b],
                    evidence=f"Shared methods: {', '.join(list(shared)[:5])}",
                ))

    return findings


# ---------------------------------------------------------------------------
# DUP-003: Import similarity
# ---------------------------------------------------------------------------

def _check_import_similarity(
    class_info: Dict[str, dict]
) -> List[ReviewFinding]:
    findings: List[ReviewFinding] = []
    classes = [
        (name, info)
        for name, info in class_info.items()
        if len(info["imports"]) >= 8
    ]

    reported: Set[Tuple[str, str]] = set()
    for i in range(len(classes)):
        for j in range(i + 1, len(classes)):
            name_a, info_a = classes[i]
            name_b, info_b = classes[j]
            sim = _jaccard(info_a["imports"], info_b["imports"])
            if sim >= IMPORT_JACCARD_THRESHOLD:
                pair = tuple(sorted([name_a, name_b]))
                if pair in reported:
                    continue
                reported.add(pair)
                findings.append(ReviewFinding(
                    category=FindingCategory.DUPLICATE,
                    severity=Severity.INFO,
                    rule_id="DUP-003",
                    title=(
                        f"Near-identical imports: {name_a} and {name_b} "
                        f"({sim*100:.0f}% overlap)"
                    ),
                    description=(
                        f"{name_a} and {name_b} share {sim*100:.0f}% of their "
                        "import statements. This may indicate duplicated utility or "
                        "infrastructure responsibilities."
                    ),
                    recommendation=(
                        "Review whether these classes share cross-cutting concerns that "
                        "could be extracted into a shared base class or utility."
                    ),
                    affected_files=[
                        info_a["file_name"],
                        info_b["file_name"],
                    ],
                    affected_classes=[name_a, name_b],
                ))

    return findings
