from __future__ import annotations

"""
SOLID Principles analyser for Java/Spring Boot codebases.

Checks implemented:
  S001  SRP -- class has too many methods
  S002  SRP -- class is too large (LOC)
  S003  SRP -- class imports from many unrelated domains
  O001  OCP -- multiple instanceof type checks (should use polymorphism)
  O002  OCP -- large if/else-if chains on type fields
  L001  LSP -- throws UnsupportedOperationException / NotImplementedException
  I001  ISP -- fat interface (too many method declarations)
  D001  DIP -- @Autowired field injection (prefer constructor injection)
  D002  DIP -- direct new ConcreteClass() instantiation of non-value objects
"""

import re
from pathlib import Path
from typing import List

from src.code_review.models import FindingCategory, ReviewFinding, Severity


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
SRP_MAX_METHODS           = 15
SRP_MAX_LOC               = 300
SRP_MAX_IMPORT_DOMAINS    = 4
SRP_MAX_IMPORTS           = 20
OCP_MIN_INSTANCEOF        = 3
OCP_MIN_ELSEIF_CHAIN      = 4
ISP_MAX_INTERFACE_METHODS = 10

_FIELD_INJECT_RE = re.compile(
    r'@Autowired\s*\n\s*(?:private|protected|public)\s+(?!static)',
    re.MULTILINE,
)
_NEW_CONCRETE_RE = re.compile(r'=\s*new\s+([A-Z][a-zA-Z0-9_]+)\s*\(', re.MULTILINE)
_INSTANCEOF_RE   = re.compile(r'\binstanceof\s+([A-Z][a-zA-Z0-9_]+)', re.MULTILINE)
_ELSEIF_RE       = re.compile(r'\belse\s+if\s*\(', re.MULTILINE)
_UNSUPPORTED_RE  = re.compile(
    r'throw\s+new\s+(?:UnsupportedOperationException|NotImplementedException)',
    re.MULTILINE,
)
_INTERFACE_METHOD_RE = re.compile(
    r'(?:public\s+)?(?:default\s+)?(?!void\s+\w+\s*=)'
    r'[a-zA-Z_$<>\[\]]+\s+\w+\s*\([^)]*\)\s*(?:throws[^;{]+)?[;{]',
    re.MULTILINE,
)

# Class types exempt from DIP/new-instance checks
_DIP_EXEMPT_SUFFIXES = (
    "Exception", "Error", "Builder", "DTO", "Dto", "Request", "Response",
    "Event", "ArrayList", "HashMap", "HashSet", "LinkedList", "LinkedHashMap",
    "StringBuilder", "StringBuffer", "Random", "Date", "BigDecimal", "BigInteger",
    "LocalDate", "LocalDateTime", "ZonedDateTime",
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_solid(metadata: List[dict], repo_root: str = "") -> List[ReviewFinding]:
    """
    Run all SOLID checks against repository metadata.

    Args:
        metadata:  List of file metadata dicts from ingest.load_metadata().
        repo_root: Repository root path for resolving relative file paths.

    Returns:
        List of ReviewFinding instances for any SOLID violations found.
    """
    findings: List[ReviewFinding] = []
    for file_meta in metadata:
        content     = _read_file(file_meta.get("file_path", ""), repo_root)
        classes     = file_meta.get("classes", [])
        interfaces  = file_meta.get("interfaces", [])
        methods     = file_meta.get("methods", [])
        imports     = file_meta.get("imports", [])
        annotations = file_meta.get("annotations", [])
        loc         = file_meta.get("lines_of_code", 0)
        file_name   = Path(file_meta.get("file_path", "unknown")).name

        for cls in classes:
            findings += _check_srp(cls, methods, imports, loc, file_name)
            if content:
                findings += _check_ocp(cls, content, file_name)
                findings += _check_lsp(cls, content, file_name)
                findings += _check_dip(cls, content, annotations, file_name)

        for iface in interfaces:
            if content:
                findings += _check_isp(iface, content, file_name)

    return findings


# ---------------------------------------------------------------------------
# Internal helpers
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


def _extract_import_domains(imports: List[str]) -> set:
    domains: set = set()
    for imp in imports:
        clean = imp.replace("import ", "").replace(";", "").strip()
        parts = clean.split(".")
        if len(parts) >= 2:
            domains.add(f"{parts[0]}.{parts[1]}")
    return domains


# ---------------------------------------------------------------------------
# S - Single Responsibility Principle
# ---------------------------------------------------------------------------

def _check_srp(
    class_name: str,
    methods: List[str],
    imports: List[str],
    loc: int,
    file_name: str,
) -> List[ReviewFinding]:
    findings: List[ReviewFinding] = []

    if len(methods) > SRP_MAX_METHODS:
        findings.append(ReviewFinding(
            category=FindingCategory.SOLID,
            severity=Severity.MEDIUM,
            rule_id="SOLID-S001",
            title=f"SRP: {class_name} has too many methods ({len(methods)})",
            description=(
                f"{class_name} defines {len(methods)} methods (threshold: {SRP_MAX_METHODS}). "
                "A class with an excessive number of methods likely handles multiple "
                "responsibilities and becomes hard to understand, test, and change."
            ),
            recommendation=(
                "Apply the Single Responsibility Principle: decompose into focused service "
                "classes, delegates, or helper utilities, each with a single reason to change."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
            evidence=f"Methods detected: {', '.join(methods[:10])}" +
                     (f"... +{len(methods)-10} more" if len(methods) > 10 else ""),
        ))

    if loc > SRP_MAX_LOC:
        severity = Severity.MEDIUM if loc > 500 else Severity.LOW
        findings.append(ReviewFinding(
            category=FindingCategory.SOLID,
            severity=severity,
            rule_id="SOLID-S002",
            title=f"SRP: {class_name} is too large ({loc} LOC)",
            description=(
                f"{class_name} spans {loc} lines of code (threshold: {SRP_MAX_LOC}). "
                "Large classes are harder to read, test, and maintain."
            ),
            recommendation=(
                "Extract cohesive groups of methods into separate, focused classes. "
                "Aim for classes under 200 LOC for typical service/repository classes."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        ))

    if len(imports) > SRP_MAX_IMPORTS:
        domains = _extract_import_domains(imports)
        if len(domains) > SRP_MAX_IMPORT_DOMAINS:
            findings.append(ReviewFinding(
                category=FindingCategory.SOLID,
                severity=Severity.LOW,
                rule_id="SOLID-S003",
                title=f"SRP: {class_name} imports from {len(domains)} domains",
                description=(
                    f"{class_name} imports from {len(domains)} distinct dependency domains "
                    f"({', '.join(sorted(domains)[:5])}). Wide imports may signal mixed concerns."
                ),
                recommendation=(
                    "Review whether all domains are required for this class's primary "
                    "responsibility. Move unrelated logic to dedicated collaborator classes."
                ),
                affected_files=[file_name],
                affected_classes=[class_name],
            ))

    return findings


# ---------------------------------------------------------------------------
# O - Open/Closed Principle
# ---------------------------------------------------------------------------

def _check_ocp(
    class_name: str,
    content: str,
    file_name: str,
) -> List[ReviewFinding]:
    findings: List[ReviewFinding] = []

    instanceof_hits = _INSTANCEOF_RE.findall(content)
    if len(instanceof_hits) >= OCP_MIN_INSTANCEOF:
        unique_types = list(dict.fromkeys(instanceof_hits))
        findings.append(ReviewFinding(
            category=FindingCategory.SOLID,
            severity=Severity.MEDIUM,
            rule_id="SOLID-O001",
            title=f"OCP: {class_name} uses {len(instanceof_hits)} instanceof checks",
            description=(
                f"{class_name} contains {len(instanceof_hits)} instanceof type checks "
                f"({', '.join(unique_types[:5])}). Adding a new type requires modifying "
                "this class, violating the Open/Closed Principle."
            ),
            recommendation=(
                "Replace conditional type-dispatch with polymorphism: define a common "
                "interface and let each type provide its own implementation."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
            evidence=f"instanceof {', '.join(unique_types[:5])}",
        ))

    elseif_count = len(_ELSEIF_RE.findall(content))
    if elseif_count >= OCP_MIN_ELSEIF_CHAIN:
        findings.append(ReviewFinding(
            category=FindingCategory.SOLID,
            severity=Severity.LOW,
            rule_id="SOLID-O002",
            title=f"OCP: {class_name} has a long else-if chain ({elseif_count} branches)",
            description=(
                f"{class_name} contains {elseif_count} else-if branches. Long conditional "
                "chains are fragile: new cases require modifying existing code."
            ),
            recommendation=(
                "Consider replacing with a Strategy pattern, a Map<key, handler>, or "
                "Spring's polymorphic dispatch."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        ))

    return findings


# ---------------------------------------------------------------------------
# L - Liskov Substitution Principle
# ---------------------------------------------------------------------------

def _check_lsp(
    class_name: str,
    content: str,
    file_name: str,
) -> List[ReviewFinding]:
    findings: List[ReviewFinding] = []

    if _UNSUPPORTED_RE.search(content):
        findings.append(ReviewFinding(
            category=FindingCategory.SOLID,
            severity=Severity.HIGH,
            rule_id="SOLID-L001",
            title=f"LSP Violation: {class_name} throws UnsupportedOperationException",
            description=(
                f"{class_name} throws UnsupportedOperationException or "
                "NotImplementedException. Substituting this class for its supertype "
                "will break callers at runtime."
            ),
            recommendation=(
                "Honour the full contract of every interface or abstract class you "
                "implement. If a method cannot be meaningfully implemented, reconsider "
                "the inheritance hierarchy or apply Interface Segregation."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        ))

    return findings


# ---------------------------------------------------------------------------
# I - Interface Segregation Principle
# ---------------------------------------------------------------------------

def _check_isp(
    interface_name: str,
    content: str,
    file_name: str,
) -> List[ReviewFinding]:
    findings: List[ReviewFinding] = []

    # Limit content to the interface body for counting
    method_count = len(_INTERFACE_METHOD_RE.findall(content))
    if method_count > ISP_MAX_INTERFACE_METHODS:
        findings.append(ReviewFinding(
            category=FindingCategory.SOLID,
            severity=Severity.MEDIUM,
            rule_id="SOLID-I001",
            title=(
                f"ISP Violation: {interface_name} declares {method_count} methods"
            ),
            description=(
                f"Interface {interface_name} has {method_count} method signatures "
                f"(threshold: {ISP_MAX_INTERFACE_METHODS}). Fat interfaces force all "
                "implementors to provide methods they may not need."
            ),
            recommendation=(
                "Split into smaller, role-specific interfaces (Role Interface pattern). "
                "Clients should only depend on the methods they actually use."
            ),
            affected_files=[file_name],
            affected_classes=[interface_name],
        ))

    return findings


# ---------------------------------------------------------------------------
# D - Dependency Inversion Principle
# ---------------------------------------------------------------------------

def _check_dip(
    class_name: str,
    content: str,
    annotations: List[str],
    file_name: str,
) -> List[ReviewFinding]:
    findings: List[ReviewFinding] = []

    # Field injection
    if _FIELD_INJECT_RE.search(content):
        findings.append(ReviewFinding(
            category=FindingCategory.SOLID,
            severity=Severity.MEDIUM,
            rule_id="SOLID-D001",
            title=f"DIP/Best Practice: {class_name} uses @Autowired field injection",
            description=(
                f"{class_name} uses @Autowired on fields, coupling the class to the "
                "Spring IoC container and preventing easy unit-test construction."
            ),
            recommendation=(
                "Use constructor injection instead: declare dependencies as private final "
                "fields and inject them through a constructor. Spring 4.3+ auto-wires "
                "single constructors without requiring an explicit @Autowired annotation."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        ))

    # Direct new ConcreteClass() instantiation
    new_instances = _NEW_CONCRETE_RE.findall(content)
    violations = [
        n for n in new_instances
        if not any(n.endswith(suffix) for suffix in _DIP_EXEMPT_SUFFIXES)
    ]
    if len(violations) >= 2:
        unique = list(dict.fromkeys(violations))
        findings.append(ReviewFinding(
            category=FindingCategory.SOLID,
            severity=Severity.LOW,
            rule_id="SOLID-D002",
            title=f"DIP: {class_name} instantiates {len(unique)} concrete class(es)",
            description=(
                f"{class_name} directly instantiates concrete classes "
                f"({', '.join(unique[:5])}), creating hidden coupling to implementations."
            ),
            recommendation=(
                "Depend on abstractions (interfaces/abstract classes) and inject "
                "concrete instances via the Spring context or a factory."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
            evidence=f"new {', new '.join(unique[:5])}()",
        ))

    return findings
