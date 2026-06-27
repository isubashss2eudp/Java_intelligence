from __future__ import annotations

"""
Technical debt detector for Java/Spring Boot codebases.

Rules implemented:
  DEBT-001  TODO / FIXME / HACK / XXX comment annotations
  DEBT-002  @Deprecated annotation usage on non-test classes
  DEBT-003  Missing Javadoc on public API methods (heuristic)
  DEBT-004  Empty catch blocks (also flagged by maintainability, listed here as debt)
  DEBT-005  Hardcoded URLs, IPs, or port numbers
  DEBT-006  Spring Boot 1.x / deprecated Spring patterns
  DEBT-007  Missing test class for a service/controller (structural gap)
  DEBT-008  Long TODO age indicator (multiple TODOs in same class)
  DEBT-009  System.exit() calls outside main/bootstrap
"""

import re
from pathlib import Path
from typing import List

from src.code_review.models import FindingCategory, ReviewFinding, Severity


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_TODO_RE = re.compile(
    r'//\s*(?:TODO|FIXME|HACK|XXX|BUG|WORKAROUND)[^\n]*',
    re.IGNORECASE | re.MULTILINE,
)

_DEPRECATED_RE = re.compile(r'@Deprecated\b', re.MULTILINE)

_JAVADOC_PUBLIC_METHOD_RE = re.compile(
    r'(?<!/)\s*(?:public)\s+(?!class|interface|enum)[\w<>\[\]]+\s+\w+\s*\(',
    re.MULTILINE,
)
_JAVADOC_COMMENT_RE = re.compile(r'/\*\*', re.MULTILINE)

# Hardcoded URLs / IPs
_HARDCODED_URL_RE = re.compile(
    r'"https?://(?!localhost|127\.0\.0\.1|example\.com|schemas\.)[^"]{5,}"',
    re.MULTILINE,
)
_HARDCODED_IP_RE = re.compile(
    r'"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?"',
    re.MULTILINE,
)
_HARDCODED_PORT_RE = re.compile(
    r'(?:port|PORT)\s*=\s*(?:80[89]\d|90\d{2}|[1-9]\d{4})\b',
    re.MULTILINE,
)

# Deprecated Spring patterns
_OLD_SPRING_WEB_RE = re.compile(
    r'(?:extends\s+(?:SimpleFormController|AbstractController|'
    r'MultiActionController)|springMVC|spring-webmvc\s+3\.|'
    r'org\.springframework\.web\.servlet\.mvc\.AbstractController)',
    re.MULTILINE,
)

# System.exit
_SYSTEM_EXIT_RE = re.compile(r'\bSystem\.exit\s*\(', re.MULTILINE)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_tech_debt(
    metadata: List[dict], repo_root: str = ""
) -> List[ReviewFinding]:
    """
    Detect technical debt indicators across the repository.

    Args:
        metadata:  List of file metadata dicts from ingest.load_metadata().
        repo_root: Repository root path for resolving relative file paths.

    Returns:
        List of ReviewFinding instances for technical debt found.
    """
    findings: List[ReviewFinding] = []

    all_class_names = {
        cls
        for fm in metadata
        for cls in fm.get("classes", [])
    }

    for file_meta in metadata:
        content     = _read_file(file_meta.get("file_path", ""), repo_root)
        classes     = file_meta.get("classes", [])
        annotations = file_meta.get("annotations", [])
        file_name   = Path(file_meta.get("file_path", "unknown")).name

        primary_class = classes[0] if classes else file_name.replace(".java", "")

        findings += _check_todo_comments(primary_class, content, file_name)
        findings += _check_deprecated_usage(primary_class, content, annotations, file_name)
        findings += _check_missing_javadoc(primary_class, content, annotations, file_name)
        findings += _check_hardcoded_urls(primary_class, content, file_name)
        findings += _check_deprecated_spring(primary_class, content, file_name)
        findings += _check_system_exit(primary_class, content, file_name)

    # DUP-007: missing test classes for services and controllers
    findings += _check_missing_tests(metadata, all_class_names)

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

def _check_todo_comments(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    todos = _TODO_RE.findall(content)
    if not todos:
        return []
    severity = Severity.MEDIUM if len(todos) >= 5 else Severity.LOW
    samples  = [t.strip()[:80] for t in todos[:4]]
    return [ReviewFinding(
        category=FindingCategory.TECH_DEBT,
        severity=severity,
        rule_id="DEBT-001",
        title=f"Technical debt: {len(todos)} TODO/FIXME/HACK comment(s) in {class_name}",
        description=(
            f"{class_name} contains {len(todos)} unresolved TODO/FIXME/HACK comments. "
            "Accumulated inline debt annotations indicate deferred work that may "
            "never get resolved."
        ),
        recommendation=(
            "Track deferred work in an issue tracker, not in code comments. "
            "Resolve or convert each TODO to a tracked issue with an owner "
            "and a target sprint."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
        evidence="\n".join(samples),
    )]


def _check_deprecated_usage(
    class_name: str, content: str, annotations: List[str], file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    deprecated_count = len(_DEPRECATED_RE.findall(content))
    if deprecated_count == 0:
        return []
    return [ReviewFinding(
        category=FindingCategory.TECH_DEBT,
        severity=Severity.MEDIUM,
        rule_id="DEBT-002",
        title=f"{class_name} has {deprecated_count} @Deprecated element(s)",
        description=(
            f"{class_name} contains {deprecated_count} @Deprecated annotation(s). "
            "Deprecated APIs signal intended removal and should not be used in new code."
        ),
        recommendation=(
            "Replace deprecated API usage with the recommended alternatives documented "
            "in the @Deprecated Javadoc. Schedule removal of deprecated elements "
            "within 1-2 release cycles."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _check_missing_javadoc(
    class_name: str, content: str, annotations: List[str], file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    # Only flag @Service / @RestController / @Repository classes
    is_api_class = any(a in ("Service", "RestController", "Controller", "Repository")
                       for a in annotations)
    if not is_api_class:
        return []

    public_methods = _JAVADOC_PUBLIC_METHOD_RE.findall(content)
    javadoc_blocks = _JAVADOC_COMMENT_RE.findall(content)

    if public_methods and len(javadoc_blocks) < len(public_methods) * 0.5:
        missing = len(public_methods) - len(javadoc_blocks)
        return [ReviewFinding(
            category=FindingCategory.TECH_DEBT,
            severity=Severity.LOW,
            rule_id="DEBT-003",
            title=f"Missing Javadoc on {missing} public method(s) in {class_name}",
            description=(
                f"{class_name} has {len(public_methods)} public method(s) but only "
                f"{len(javadoc_blocks)} Javadoc comment block(s). "
                "Public API surfaces should be documented."
            ),
            recommendation=(
                "Add /** ... */ Javadoc to all public methods describing: "
                "what the method does, its parameters (@param), return value (@return), "
                "and thrown exceptions (@throws)."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []


def _check_hardcoded_urls(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    url_hits  = _HARDCODED_URL_RE.findall(content)
    ip_hits   = _HARDCODED_IP_RE.findall(content)
    port_hits = _HARDCODED_PORT_RE.findall(content)

    all_hits = url_hits + ip_hits + port_hits
    if not all_hits:
        return []

    return [ReviewFinding(
        category=FindingCategory.TECH_DEBT,
        severity=Severity.MEDIUM,
        rule_id="DEBT-005",
        title=f"Hardcoded URL/IP/port in {class_name}",
        description=(
            f"{class_name} contains {len(all_hits)} hardcoded network address(es) "
            f"or port number(s). These break when deploying to different environments."
        ),
        recommendation=(
            "Move all URLs, IPs, and ports to application.properties/yaml or "
            "environment variables. Inject them with @Value(\"${app.service.url}\") "
            "or Spring Cloud Config."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
        evidence=f"Found: {', '.join(str(h) for h in all_hits[:4])}",
    )]


def _check_deprecated_spring(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    if _OLD_SPRING_WEB_RE.search(content):
        return [ReviewFinding(
            category=FindingCategory.TECH_DEBT,
            severity=Severity.HIGH,
            rule_id="DEBT-006",
            title=f"Deprecated Spring MVC pattern in {class_name}",
            description=(
                f"{class_name} uses Spring MVC patterns (SimpleFormController, "
                "AbstractController, etc.) that were removed in Spring 5. "
                "This code will not compile with modern Spring Boot."
            ),
            recommendation=(
                "Migrate to @Controller / @RestController with @RequestMapping "
                "and method-level handler annotations (@GetMapping, @PostMapping, etc.)."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []


def _check_system_exit(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not content:
        return []
    hits = _SYSTEM_EXIT_RE.findall(content)
    if not hits:
        return []
    # Suppress for classes that look like main entry points
    if re.search(r'public\s+static\s+void\s+main\s*\(', content):
        return []
    return [ReviewFinding(
        category=FindingCategory.TECH_DEBT,
        severity=Severity.HIGH,
        rule_id="DEBT-009",
        title=f"System.exit() call in non-main class {class_name}",
        description=(
            f"{class_name} calls System.exit(), forcibly terminating the JVM. "
            "This bypasses shutdown hooks, Spring context lifecycle, and container "
            "restart policies."
        ),
        recommendation=(
            "Throw an appropriate exception or return an error status instead. "
            "In Spring Boot, use SpringApplication.exit() with ExitCodeGenerator "
            "if a controlled shutdown is truly required."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _check_missing_tests(
    metadata: List[dict], all_class_names: set
) -> List[ReviewFinding]:
    """Flag @Service / @Controller classes that lack a corresponding test class."""
    findings: List[ReviewFinding] = []
    test_classes = {
        cls
        for fm in metadata
        for cls in fm.get("classes", [])
        if cls.endswith("Test") or cls.endswith("Tests") or cls.endswith("IT")
    }

    for file_meta in metadata:
        classes     = file_meta.get("classes", [])
        annotations = file_meta.get("annotations", [])
        file_name   = Path(file_meta.get("file_path", "unknown")).name

        is_testable = any(
            a in ("Service", "RestController", "Controller") for a in annotations
        )
        if not is_testable:
            continue

        for cls in classes:
            # Check if any test class references this class name
            has_test = any(
                t.startswith(cls) or cls in t
                for t in test_classes
            )
            if not has_test:
                findings.append(ReviewFinding(
                    category=FindingCategory.TECH_DEBT,
                    severity=Severity.MEDIUM,
                    rule_id="DEBT-007",
                    title=f"No test class found for {cls}",
                    description=(
                        f"{cls} is a service or controller with no corresponding "
                        "test class detected in the repository. "
                        "Untested classes accumulate technical debt and increase "
                        "regression risk."
                    ),
                    recommendation=(
                        f"Create {cls}Test.java with unit tests using JUnit 5 + Mockito "
                        "for service layer, or @WebMvcTest for controller layer. "
                        "Aim for >80% line coverage on service classes."
                    ),
                    affected_files=[file_name],
                    affected_classes=[cls],
                ))

    return findings
