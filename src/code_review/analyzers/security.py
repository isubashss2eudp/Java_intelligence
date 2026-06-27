from __future__ import annotations

"""
Security vulnerability analyser for Java/Spring Boot codebases.

Rules implemented (OWASP-aligned):
  SEC-001  SQL injection via string concatenation in query strings
  SEC-002  Hardcoded credentials / secrets in source code
  SEC-003  Missing @Valid / @Validated on controller request bodies
  SEC-004  Sensitive data logged via System.out or logger without masking
  SEC-005  Weak cryptographic algorithms (MD5, SHA-1, DES, 3DES)
  SEC-006  Insecure random (java.util.Random for security-sensitive context)
  SEC-007  Deserialization without type restriction (ObjectInputStream)
  SEC-008  Path traversal risk (unchecked user input in file paths)
  SEC-009  Missing security annotations on REST controllers (@PreAuthorize etc.)
  SEC-010  Spring Security CSRF disabled in configuration
"""

import re
from pathlib import Path
from typing import List

from src.code_review.models import FindingCategory, ReviewFinding, Severity


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# SQL injection: string concatenation inside query strings
_SQL_CONCAT_RE = re.compile(
    r'(?:query|sql|hql|jpql|nativeQuery|createQuery|createNativeQuery)'
    r'[^;]*?"[^"]*"\s*\+',
    re.IGNORECASE | re.MULTILINE,
)

# Hardcoded credentials pattern
_HARDCODED_CRED_RE = re.compile(
    r'(?:password|passwd|secret|api[_-]?key|token|credential|auth)'
    r'\s*=\s*"[^"]{4,}"',
    re.IGNORECASE | re.MULTILINE,
)

# Controller request body without @Valid
_REQUEST_BODY_NO_VALID_RE = re.compile(
    r'@RequestBody\s+(?!.*@Valid)(?:[A-Z]\w+)\s+\w+',
    re.MULTILINE,
)
# More precise: @RequestBody without @Valid nearby
_REQUEST_BODY_RE = re.compile(r'@RequestBody', re.MULTILINE)
_VALID_RE        = re.compile(r'@(?:Valid|Validated)\b', re.MULTILINE)

# Sensitive data logging
_SENSITIVE_LOG_RE = re.compile(
    r'(?:log|logger|LOG)\s*\.\s*(?:info|debug|warn|error|trace)\s*\([^)]*'
    r'(?:password|passwd|secret|token|credential|credit[_-]?card)',
    re.IGNORECASE | re.MULTILINE,
)
_SYSOUT_SENSITIVE_RE = re.compile(
    r'System\.out\.(?:print|println)\s*\([^)]*'
    r'(?:password|passwd|secret|token|credential)',
    re.IGNORECASE | re.MULTILINE,
)

# Weak cryptography
_WEAK_CRYPTO_RE = re.compile(
    r'(?:getInstance|getMessageDigest)\s*\(\s*"(?:MD5|SHA-?1|DES|3DES|RC4|RC2)"',
    re.IGNORECASE | re.MULTILINE,
)

# Insecure random usage
_INSECURE_RANDOM_RE = re.compile(
    r'new\s+java\.util\.Random\s*\(\s*\)|new\s+Random\s*\(\s*\)',
    re.MULTILINE,
)
# Only flag if it's near security-sensitive words
_SECURITY_CONTEXT_RE = re.compile(
    r'(?:token|session|nonce|salt|key|secret|otp|password)',
    re.IGNORECASE,
)

# ObjectInputStream deserialization
_DESERIALIZATION_RE = re.compile(
    r'new\s+ObjectInputStream\s*\(|\.readObject\s*\(',
    re.MULTILINE,
)

# Path traversal: user input used in file path
_PATH_TRAVERSAL_RE = re.compile(
    r'new\s+(?:File|FileInputStream|FileOutputStream|Path)\s*\('
    r'[^)]*(?:getParameter|getPathVariable|requestParam|param)',
    re.IGNORECASE | re.MULTILINE,
)

# Missing security annotation on RestController
_REST_CONTROLLER_RE = re.compile(r'@(?:RestController|Controller)\b')
_SECURITY_ANNO_RE   = re.compile(
    r'@(?:PreAuthorize|PostAuthorize|Secured|RolesAllowed|PermitAll|DenyAll)',
)

# CSRF disabled in Security configuration
_CSRF_DISABLED_RE = re.compile(r'\.csrf\s*\(\s*\w*\s*->\s*\w+\.disable\s*\(\s*\)')


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_security(metadata: List[dict], repo_root: str = "") -> List[ReviewFinding]:
    """
    Run all security checks against repository metadata.

    Args:
        metadata:  List of file metadata dicts from ingest.load_metadata().
        repo_root: Repository root path for resolving relative file paths.

    Returns:
        List of ReviewFinding instances for any security issues found.
    """
    findings: List[ReviewFinding] = []
    for file_meta in metadata:
        content   = _read_file(file_meta.get("file_path", ""), repo_root)
        classes   = file_meta.get("classes", [])
        file_name = Path(file_meta.get("file_path", "unknown")).name
        annotations = file_meta.get("annotations", [])

        if not content:
            continue

        for cls in classes:
            findings += _check_sql_injection(cls, content, file_name)
            findings += _check_hardcoded_creds(cls, content, file_name)
            findings += _check_sensitive_logging(cls, content, file_name)
            findings += _check_weak_crypto(cls, content, file_name)
            findings += _check_insecure_random(cls, content, file_name)
            findings += _check_deserialization(cls, content, file_name)
            findings += _check_path_traversal(cls, content, file_name)
            findings += _check_missing_input_validation(cls, content, annotations, file_name)
            findings += _check_missing_security_annotations(cls, content, annotations, file_name)

        findings += _check_csrf_disabled(content, file_name)

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


def _line_numbers(content: str, pattern: re.Pattern) -> List[int]:
    lines = content.splitlines()
    hits  = []
    for i, line in enumerate(lines, 1):
        if pattern.search(line):
            hits.append(i)
    return hits[:10]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_sql_injection(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not _SQL_CONCAT_RE.search(content):
        return []
    hits = _line_numbers(content, _SQL_CONCAT_RE)
    return [ReviewFinding(
        category=FindingCategory.SECURITY,
        severity=Severity.CRITICAL,
        rule_id="SEC-001",
        title=f"SQL Injection risk in {class_name}",
        description=(
            f"{class_name} appears to build SQL/JPQL queries via string concatenation. "
            "User-controlled input in query strings is the classic SQL injection vector."
        ),
        recommendation=(
            "Use parameterised queries exclusively: JPA named parameters (:param), "
            "Spring Data @Query with ?1 positional params, or Criteria API. "
            "Never concatenate user input into query strings."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
        line_numbers=hits,
        evidence=f"String concatenation detected near query keyword at lines {hits}",
    )]


def _check_hardcoded_creds(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    matches = _HARDCODED_CRED_RE.findall(content)
    if not matches:
        return []
    redacted = [m.split("=")[0].strip() for m in matches[:3]]
    return [ReviewFinding(
        category=FindingCategory.SECURITY,
        severity=Severity.CRITICAL,
        rule_id="SEC-002",
        title=f"Hardcoded credential in {class_name}",
        description=(
            f"{class_name} contains hardcoded credential assignments "
            f"({', '.join(redacted)}). Committing secrets to source control "
            "exposes them to anyone with repository access."
        ),
        recommendation=(
            "Store credentials in environment variables or a secret manager "
            "(Vault, AWS Secrets Manager, etc.). Reference them via @Value(\"${...}\") "
            "or Spring Cloud Config. Never embed secrets in source code."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
        evidence=f"Fields: {', '.join(redacted)}",
    )]


def _check_sensitive_logging(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    findings = []
    if _SENSITIVE_LOG_RE.search(content) or _SYSOUT_SENSITIVE_RE.search(content):
        findings.append(ReviewFinding(
            category=FindingCategory.SECURITY,
            severity=Severity.HIGH,
            rule_id="SEC-004",
            title=f"Sensitive data logging in {class_name}",
            description=(
                f"{class_name} logs or prints potentially sensitive fields "
                "(password, secret, token, credential). Log data may be stored "
                "insecurely or visible to unauthorised users."
            ),
            recommendation=(
                "Mask or redact sensitive fields before logging. "
                "Never log passwords, tokens, or credit card numbers. "
                "Use structured logging with explicit field exclusion policies."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        ))
    return findings


def _check_weak_crypto(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    matches = _WEAK_CRYPTO_RE.findall(content)
    if not matches:
        return []
    algos = list(dict.fromkeys(matches))
    return [ReviewFinding(
        category=FindingCategory.SECURITY,
        severity=Severity.HIGH,
        rule_id="SEC-005",
        title=f"Weak cryptographic algorithm in {class_name}: {', '.join(algos)}",
        description=(
            f"{class_name} uses broken or weak cryptographic algorithm(s): "
            f"{', '.join(algos)}. These are considered cryptographically broken "
            "and must not be used for security-sensitive operations."
        ),
        recommendation=(
            "Replace MD5/SHA-1 with SHA-256 or SHA-3 for hashing. "
            "Replace DES/3DES with AES-256-GCM. "
            "For password storage use BCrypt, Argon2, or PBKDF2."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
        evidence=f"Algorithms found: {', '.join(algos)}",
    )]


def _check_insecure_random(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not _INSECURE_RANDOM_RE.search(content):
        return []
    # Only flag when it occurs in a security-sensitive context
    if not _SECURITY_CONTEXT_RE.search(content):
        return []
    return [ReviewFinding(
        category=FindingCategory.SECURITY,
        severity=Severity.MEDIUM,
        rule_id="SEC-006",
        title=f"Insecure random in {class_name}",
        description=(
            f"{class_name} uses java.util.Random which is not cryptographically "
            "secure. Predictable random values are exploitable in token generation, "
            "session IDs, and security nonces."
        ),
        recommendation=(
            "Use java.security.SecureRandom for any security-sensitive random "
            "number generation (tokens, OTPs, salts, session identifiers)."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _check_deserialization(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not _DESERIALIZATION_RE.search(content):
        return []
    return [ReviewFinding(
        category=FindingCategory.SECURITY,
        severity=Severity.HIGH,
        rule_id="SEC-007",
        title=f"Unsafe deserialization in {class_name}",
        description=(
            f"{class_name} uses Java ObjectInputStream or readObject() for "
            "deserialization without apparent type filtering. Deserializing untrusted "
            "data is a remote code execution vector."
        ),
        recommendation=(
            "Avoid native Java deserialization of untrusted data. "
            "If required, implement a LookAheadObjectInputStream that whitelists "
            "expected types. Prefer JSON/protobuf with schema validation."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _check_path_traversal(
    class_name: str, content: str, file_name: str
) -> List[ReviewFinding]:
    if not _PATH_TRAVERSAL_RE.search(content):
        return []
    return [ReviewFinding(
        category=FindingCategory.SECURITY,
        severity=Severity.HIGH,
        rule_id="SEC-008",
        title=f"Path traversal risk in {class_name}",
        description=(
            f"{class_name} constructs file paths using what appears to be "
            "user-supplied input. An attacker could use '../' sequences to access "
            "files outside the intended directory."
        ),
        recommendation=(
            "Validate and sanitise all user-supplied file paths. "
            "Use Path.normalize() and verify the resolved path starts within "
            "the allowed base directory. Reject paths containing '..'."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _check_missing_input_validation(
    class_name: str, content: str, annotations: List[str], file_name: str
) -> List[ReviewFinding]:
    # Only check @RestController / @Controller classes
    if not _REST_CONTROLLER_RE.search(content):
        return []

    request_body_count = len(_REQUEST_BODY_RE.findall(content))
    valid_count        = len(_VALID_RE.findall(content))

    if request_body_count > 0 and valid_count < request_body_count:
        missing = request_body_count - valid_count
        return [ReviewFinding(
            category=FindingCategory.SECURITY,
            severity=Severity.MEDIUM,
            rule_id="SEC-003",
            title=f"Missing @Valid on {missing} @RequestBody parameter(s) in {class_name}",
            description=(
                f"{class_name} has {request_body_count} @RequestBody parameter(s) "
                f"but only {valid_count} @Valid annotation(s). "
                "Unvalidated input bypasses bean validation constraints."
            ),
            recommendation=(
                "Add @Valid (or @Validated) before every @RequestBody parameter. "
                "Define JSR-380 constraint annotations on the DTO fields. "
                "Handle MethodArgumentNotValidException in a @ControllerAdvice."
            ),
            affected_files=[file_name],
            affected_classes=[class_name],
        )]
    return []


def _check_missing_security_annotations(
    class_name: str, content: str, annotations: List[str], file_name: str
) -> List[ReviewFinding]:
    if not _REST_CONTROLLER_RE.search(content):
        return []
    if _SECURITY_ANNO_RE.search(content):
        return []
    # Heuristic: if the controller doesn't have any Spring Security annotation
    # and doesn't seem to be a public endpoint (no obvious PermitAll pattern),
    # flag it as an informational finding
    return [ReviewFinding(
        category=FindingCategory.SECURITY,
        severity=Severity.INFO,
        rule_id="SEC-009",
        title=f"No method-level security annotation in {class_name}",
        description=(
            f"{class_name} is a REST controller with no @PreAuthorize, "
            "@PostAuthorize, @Secured, or @RolesAllowed annotations on its methods. "
            "Endpoint authorisation may rely solely on URL-pattern security config."
        ),
        recommendation=(
            "Apply @PreAuthorize(\"hasRole('...')\") on sensitive endpoints. "
            "Method-level security provides defence-in-depth beyond URL patterns "
            "and is enforced regardless of how the method is called."
        ),
        affected_files=[file_name],
        affected_classes=[class_name],
    )]


def _check_csrf_disabled(content: str, file_name: str) -> List[ReviewFinding]:
    if not _CSRF_DISABLED_RE.search(content):
        return []
    return [ReviewFinding(
        category=FindingCategory.SECURITY,
        severity=Severity.HIGH,
        rule_id="SEC-010",
        title=f"CSRF protection disabled in {file_name}",
        description=(
            "Spring Security CSRF protection is explicitly disabled. "
            "This exposes stateful session-based endpoints to cross-site "
            "request forgery attacks."
        ),
        recommendation=(
            "Only disable CSRF for stateless REST APIs that use token-based "
            "authentication (JWT/OAuth2). For session-based UIs, keep CSRF "
            "protection enabled or implement SameSite cookie policies."
        ),
        affected_files=[file_name],
        affected_classes=[],
    )]
