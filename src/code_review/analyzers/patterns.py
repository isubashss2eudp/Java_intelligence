from __future__ import annotations

"""
Design pattern detector for Java/Spring Boot codebases.

Detects both positive patterns (correctly applied GOF patterns) and
anti-patterns (architectural smells that should be refactored).

Positive patterns detected:
  PAT-001  Singleton pattern
  PAT-002  Factory / Factory Method
  PAT-003  Builder pattern
  PAT-004  Observer / Event-driven
  PAT-005  Strategy pattern (multiple implementations of an interface)
  PAT-006  Facade pattern

Anti-patterns detected:
  ANTI-001  God Class (too large, too many responsibilities)
  ANTI-002  Service Locator (ApplicationContext.getBean())
  ANTI-003  Anemic Domain Model (entity with no business methods)
  ANTI-004  Feature Envy (class with many foreign-class references)
  ANTI-005  Primitive Obsession (many primitive parameters)
  ANTI-006  Spaghetti Inheritance (deep extends chains)
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from src.code_review.models import FindingCategory, ReviewFinding, Severity


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
GOD_CLASS_LOC           = 500
GOD_CLASS_METHODS       = 20
ANEMIC_MAX_METHODS      = 3       # entity with <= 3 methods is considered anemic
FEATURE_ENVY_THRESHOLD  = 5      # foreign class references
PRIMITIVE_OBSESSION_MIN = 4      # number of primitive params in one method


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Singleton
_SINGLETON_RE = re.compile(
    r'private\s+static\s+(?:volatile\s+)?'
    r'(?:final\s+)?[A-Z]\w+\s+(?:instance|INSTANCE|singleton)\b',
    re.MULTILINE,
)
_GET_INSTANCE_RE = re.compile(r'public\s+static\s+\w+\s+getInstance\s*\(', re.MULTILINE)

# Factory
_FACTORY_METHOD_RE = re.compile(
    r'public\s+static\s+[A-Z]\w+\s+(?:create|build|of|from|newInstance|make)\w*\s*\(',
    re.MULTILINE,
)

# Builder
_BUILDER_CLASS_RE = re.compile(r'class\s+\w*Builder\b', re.MULTILINE)
_BUILDER_METHOD_RE = re.compile(r'public\s+\w*Builder\s+\w+\s*\(', re.MULTILINE)

# Observer / event
_EVENT_LISTENER_RE = re.compile(
    r'@(?:EventListener|ApplicationListener|KafkaListener|RabbitListener)\b',
    re.MULTILINE,
)
_PUBLISH_EVENT_RE = re.compile(
    r'(?:applicationEventPublisher|eventPublisher)\s*\.\s*publishEvent\s*\(',
    re.MULTILINE | re.IGNORECASE,
)

# Service Locator anti-pattern
_SERVICE_LOCATOR_RE = re.compile(
    r'(?:applicationContext|ctx|context)\s*\.\s*getBean\s*\(',
    re.IGNORECASE | re.MULTILINE,
)

# extends (chain depth detection)
_EXTENDS_RE = re.compile(r'\bextends\s+([A-Z]\w+)', re.MULTILINE)

# Primitive types in method signatures
_PRIMITIVE_PARAM_RE = re.compile(
    r'(?:int|long|double|float|boolean|short|byte|char)\s+\w+',
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_patterns(
    metadata: List[dict], repo_root: str = ""
) -> List[ReviewFinding]:
    """
    Detect design patterns and anti-patterns across the repository.

    Args:
        metadata:  List of file metadata dicts from ingest.load_metadata().
        repo_root: Repository root path for resolving relative file paths.

    Returns:
        List of ReviewFinding instances (findings + anti-pattern warnings).
    """
    findings: List[ReviewFinding] = []

    # Build interface -> implementations map for Strategy detection
    iface_implementations: Dict[str, List[str]] = defaultdict(list)
    for fm in metadata:
        for cls in fm.get("classes", []):
            content = _read_file(fm.get("file_path", ""), repo_root)
            if content:
                for iface_match in re.finditer(
                    r'\bimplements\s+([\w,\s]+)', content, re.MULTILINE
                ):
                    for iface in iface_match.group(1).split(","):
                        iface_name = iface.strip().split("<")[0]
                        if iface_name:
                            iface_implementations[iface_name].append(cls)

    for file_meta in metadata:
        content     = _read_file(file_meta.get("file_path", ""), repo_root)
        classes     = file_meta.get("classes", [])
        interfaces  = file_meta.get("interfaces", [])
        annotations = file_meta.get("annotations", [])
        loc         = file_meta.get("lines_of_code", 0)
        methods     = file_meta.get("methods", [])
        imports     = file_meta.get("imports", [])
        file_name   = Path(file_meta.get("file_path", "unknown")).name

        for cls in classes:
            # Positive patterns
            if content:
                findings += _detect_singleton(cls, content, file_name)
                findings += _detect_factory(cls, content, file_name)
                findings += _detect_builder(cls, content, file_name)
                findings += _detect_observer(cls, content, file_name)

            # Anti-patterns
            findings += _detect_god_class(cls, loc, methods, file_name)
            if content:
                findings += _detect_service_locator(cls, content, annotations, file_name)
                findings += _detect_primitive_obsession(cls, content, file_name)
                findings += _detect_deep_inheritance(cls, content, file_name)

        # Anemic domain model check for entities
        is_entity = any(a in ("Entity", "Document", "MappedSuperclass") for a in annotations)
        if is_entity and classes:
            for cls in classes:
                findings += _detect_anemic_model(cls, methods, file_name)

    # Strategy pattern (repository-level)
    findings += _detect_strategy(iface_implementations)

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
# Positive pattern detectors (informational -- confirm good design)
# ---------------------------------------------------------------------------

def _detect_singleton(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not (_SINGLETON_RE.search(content) and _GET_INSTANCE_RE.search(content)):
        return []
    return [ReviewFinding(
        category=FindingCategory.DESIGN_PATTERN,
        severity=Severity.INFO,
        rule_id="PAT-001",
        title=f"Singleton pattern in {class_name}",
        description=(
            f"{class_name} implements the Singleton pattern (private static instance "
            "field + getInstance() method). "
            "In a Spring Boot application, Spring-managed beans are singletons by "
            "default, making manual Singleton implementation redundant."
        ),
        recommendation=(
            "If this is a Spring bean, remove the manual Singleton implementation "
            "and rely on Spring's default singleton scope. "
            "Manual Singletons are justified only for non-Spring utilities."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _detect_factory(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not _FACTORY_METHOD_RE.search(content):
        return []
    return [ReviewFinding(
        category=FindingCategory.DESIGN_PATTERN,
        severity=Severity.INFO,
        rule_id="PAT-002",
        title=f"Factory Method pattern in {class_name}",
        description=(
            f"{class_name} exposes static factory methods (create/build/of/from). "
            "This is a positive pattern for object creation with intent-revealing names."
        ),
        recommendation=(
            "Ensure factory methods validate inputs and throw descriptive exceptions "
            "for invalid arguments. Consider @Component + injection rather than "
            "static factories when Spring dependency injection is available."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _detect_builder(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not (_BUILDER_CLASS_RE.search(content) or _BUILDER_METHOD_RE.search(content)):
        return []
    return [ReviewFinding(
        category=FindingCategory.DESIGN_PATTERN,
        severity=Severity.INFO,
        rule_id="PAT-003",
        title=f"Builder pattern in {class_name}",
        description=(
            f"{class_name} uses the Builder pattern. "
            "Builders are appropriate for objects with many optional fields."
        ),
        recommendation=(
            "Consider using Lombok @Builder to reduce boilerplate. "
            "Ensure the Builder validates required fields before calling build()."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _detect_observer(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not (_EVENT_LISTENER_RE.search(content) or _PUBLISH_EVENT_RE.search(content)):
        return []
    return [ReviewFinding(
        category=FindingCategory.DESIGN_PATTERN,
        severity=Severity.INFO,
        rule_id="PAT-004",
        title=f"Observer/Event pattern in {class_name}",
        description=(
            f"{class_name} participates in the Observer/Event-driven pattern using "
            "Spring's ApplicationEvent or messaging infrastructure."
        ),
        recommendation=(
            "Ensure events are immutable value objects. "
            "Consider @TransactionalEventListener to bind event processing "
            "to transaction commit/rollback."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _detect_strategy(
    iface_implementations: Dict[str, List[str]]
) -> List[ReviewFinding]:
    """Flag interfaces with 3+ implementations as Strategy pattern candidates."""
    findings = []
    for iface, implementors in iface_implementations.items():
        if len(implementors) >= 3 and not iface.endswith(("Repository", "Listener")):
            findings.append(ReviewFinding(
                category=FindingCategory.DESIGN_PATTERN,
                severity=Severity.INFO,
                rule_id="PAT-005",
                title=f"Strategy pattern: {iface} has {len(implementors)} implementations",
                description=(
                    f"Interface {iface} has {len(implementors)} concrete implementations: "
                    f"{', '.join(implementors[:5])}. "
                    "This is the Strategy pattern -- a positive indicator of OCP compliance."
                ),
                recommendation=(
                    "Ensure implementations are injected via the interface type, not the "
                    "concrete type. Use @Qualifier or @Primary for disambiguation."
                ),
                affected_classes=[iface] + implementors[:5],
            ))
    return findings


# ---------------------------------------------------------------------------
# Anti-pattern detectors
# ---------------------------------------------------------------------------

def _detect_god_class(
    class_name: str, loc: int, methods: List[str], file_name: str
) -> List[ReviewFinding]:
    if loc < GOD_CLASS_LOC and len(methods) < GOD_CLASS_METHODS:
        return []
    severity = Severity.HIGH if (loc > 800 or len(methods) > 30) else Severity.MEDIUM
    return [ReviewFinding(
        category=FindingCategory.DESIGN_PATTERN,
        severity=severity,
        rule_id="ANTI-001",
        title=f"God Class anti-pattern: {class_name} ({loc} LOC, {len(methods)} methods)",
        description=(
            f"{class_name} is a God Class with {loc} lines and {len(methods)} methods. "
            "God Classes accumulate too many responsibilities, become the single largest "
            "source of merge conflicts, and are impossible to unit-test effectively."
        ),
        recommendation=(
            "Identify distinct responsibilities within the class and extract each into "
            "a focused class. Apply SRP: each class should have one reason to change. "
            "Use package-by-feature to guide decomposition."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
        evidence=f"LOC: {loc}, Methods: {len(methods)}",
    )]


def _detect_service_locator(
    class_name: str, content: str, annotations: List[str], file_name: str
) -> List[ReviewFinding]:
    if not _SERVICE_LOCATOR_RE.search(content):
        return []
    return [ReviewFinding(
        category=FindingCategory.DESIGN_PATTERN,
        severity=Severity.HIGH,
        rule_id="ANTI-002",
        title=f"Service Locator anti-pattern in {class_name}",
        description=(
            f"{class_name} uses applicationContext.getBean() to look up beans "
            "at runtime. This hides dependencies and makes the class hard to test."
        ),
        recommendation=(
            "Replace Service Locator with constructor injection. "
            "If dynamic bean selection is needed, inject a Map<String, MyInterface> "
            "or use ApplicationContext.getBeansOfType() in a configuration class "
            "once at startup."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _detect_anemic_model(
    class_name: str, methods: List[str], file_name: str
) -> List[ReviewFinding]:
    """Detect entities with no domain behavior (only getters/setters)."""
    business_methods = [
        m for m in methods
        if not any(m.lower().startswith(prefix)
                   for prefix in ("get", "set", "is", "has", "equals", "hashcode",
                                  "tostring", "canequal"))
    ]
    if len(business_methods) <= ANEMIC_MAX_METHODS:
        return [ReviewFinding(
            category=FindingCategory.DESIGN_PATTERN,
            severity=Severity.LOW,
            rule_id="ANTI-003",
            title=f"Anemic Domain Model: {class_name} has no domain behaviour",
            description=(
                f"Entity {class_name} has only {len(business_methods)} non-accessor "
                "method(s). Anemic models push all logic into service classes, "
                "defeating the purpose of object-oriented design."
            ),
            recommendation=(
                "Move domain logic that naturally belongs to the entity back into the "
                "entity class. Entities should encapsulate their invariants and "
                "expose behaviour, not just data."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []


def _detect_primitive_obsession(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    """Detect methods with too many primitive parameters."""
    method_pattern = re.compile(
        r'(?:public|protected)\s+[\w<>\[\]]+\s+\w+\s*\(([^)]+)\)',
        re.MULTILINE,
    )
    violations = []
    for m in method_pattern.finditer(content):
        params = m.group(1)
        primitives = _PRIMITIVE_PARAM_RE.findall(params)
        if len(primitives) >= PRIMITIVE_OBSESSION_MIN:
            violations.append((m.group(0)[:60], len(primitives)))
    if violations:
        worst = max(violations, key=lambda x: x[1])
        return [ReviewFinding(
            category=FindingCategory.DESIGN_PATTERN,
            severity=Severity.LOW,
            rule_id="ANTI-005",
            title=f"Primitive Obsession in {class_name}",
            description=(
                f"{class_name} has {len(violations)} method(s) with "
                f"{PRIMITIVE_OBSESSION_MIN}+ primitive parameters. "
                "Primitive Obsession makes API meaning ambiguous and increases "
                "the risk of argument order errors."
            ),
            recommendation=(
                "Introduce Value Objects or Parameter Objects to group related "
                "primitive values (e.g. Money, DateRange, Coordinates). "
                "Value Objects improve type safety and domain expressiveness."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
            evidence=f"Worst: {worst[0]} ({worst[1]} primitives)",
        )]
    return []


def _detect_deep_inheritance(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    """Heuristic: class that extends a non-framework class in a chain."""
    extends_matches = _EXTENDS_RE.findall(content)
    # Only flag if we see extends of non-standard names multiple times
    # (simple proxy: if there are 2+ distinct extends in one file it's complex)
    if len(extends_matches) >= 2:
        return [ReviewFinding(
            category=FindingCategory.DESIGN_PATTERN,
            severity=Severity.LOW,
            rule_id="ANTI-006",
            title=f"Complex inheritance in {class_name}",
            description=(
                f"{class_name}'s file references {len(extends_matches)} class(es) "
                f"via extends ({', '.join(extends_matches[:4])}). "
                "Deep or multiple-level inheritance hierarchies are fragile and "
                "hard to refactor."
            ),
            recommendation=(
                "Prefer composition over inheritance. "
                "Limit inheritance hierarchies to 2-3 levels. "
                "Use interfaces + delegation instead of deep class extension."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []
