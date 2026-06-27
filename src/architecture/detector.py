from __future__ import annotations

"""
Java class role detector for Spring Boot applications.

Detection priority (highest wins):
  1. Annotations  -- @Service, @RestController, @Entity, etc.
  2. Interface    -- extends JpaRepository -> repository
  3. Naming       -- OrderService suffix, UserDTO suffix
  4. Package      -- package com.x.service -> service hint
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Detection tables
# ---------------------------------------------------------------------------

# Spring / JPA annotation -> (role, confidence)
ANNOTATION_ROLES: Dict[str, Tuple[str, str]] = {
    "RestController":        ("controller",    "high"),
    "Controller":            ("controller",    "high"),
    "RequestMapping":        ("controller",    "medium"),
    "Service":               ("service",       "high"),
    "Repository":            ("repository",    "high"),
    "Entity":                ("entity",        "high"),
    "Table":                 ("entity",        "high"),
    "Document":              ("entity",        "high"),
    "MappedSuperclass":      ("entity",        "high"),
    "Embeddable":            ("entity",        "medium"),
    "Configuration":         ("configuration", "high"),
    "SpringBootApplication": ("main",          "high"),
    "EnableAutoConfiguration": ("main",        "high"),
    "Component":             ("component",     "medium"),
    "Mapper":                ("component",     "medium"),
    "Aspect":                ("component",     "medium"),
    "EventListener":         ("component",     "medium"),
    "Scheduled":             ("component",     "medium"),
}

# Class name suffix -> role  (sorted by descending length at runtime)
SUFFIX_ROLES: Dict[str, str] = {
    "Controller":     "controller",
    "Resource":       "controller",
    "Endpoint":       "controller",
    "Service":        "service",
    "ServiceImpl":    "service",
    "Facade":         "service",
    "Repository":     "repository",
    "RepositoryImpl": "repository",
    "Dao":            "repository",
    "DAO":            "repository",
    "Store":          "repository",
    "Entity":         "entity",
    "DTO":            "dto",
    "Dto":            "dto",
    "Request":        "dto",
    "Response":       "dto",
    "Payload":        "dto",
    "Form":           "dto",
    "Config":         "configuration",
    "Configuration":  "configuration",
    "Properties":     "configuration",
    "Settings":       "configuration",
    "Exception":      "exception",
    "Error":          "exception",
    "Util":           "utility",
    "Utils":          "utility",
    "Helper":         "utility",
    "Constants":      "utility",
    "Constant":       "utility",
}

# Package name segment (lowercased) -> role hint
PACKAGE_HINTS: Dict[str, str] = {
    "controller":   "controller",
    "controllers":  "controller",
    "web":          "controller",
    "rest":         "controller",
    "api":          "controller",
    "resource":     "controller",
    "service":      "service",
    "services":     "service",
    "business":     "service",
    "repository":   "repository",
    "repositories": "repository",
    "repo":         "repository",
    "dao":          "repository",
    "persistence":  "repository",
    "entity":       "entity",
    "entities":     "entity",
    "domain":       "entity",
    "model":        "entity",
    "models":       "entity",
    "dto":          "dto",
    "dtos":         "dto",
    "transfer":     "dto",
    "request":      "dto",
    "response":     "dto",
    "config":       "configuration",
    "configuration":"configuration",
    "exception":    "exception",
    "exceptions":   "exception",
    "util":         "utility",
    "utils":        "utility",
    "common":       "utility",
    "shared":       "utility",
    "security":     "security",
    "auth":         "security",
}

# Well-known Spring Data super-interfaces
REPO_INTERFACES = frozenset({
    "JpaRepository",
    "CrudRepository",
    "PagingAndSortingRepository",
    "MongoRepository",
    "ReactiveMongoRepository",
    "R2dbcRepository",
    "ElasticsearchRepository",
    "ReactiveCrudRepository",
})

# Human-readable labels for roles
ROLE_LABELS: Dict[str, str] = {
    "controller":    "Controllers",
    "service":       "Services",
    "repository":    "Repositories",
    "entity":        "Entities",
    "dto":           "DTOs",
    "configuration": "Configuration",
    "component":     "Components",
    "exception":     "Exceptions",
    "utility":       "Utilities",
    "security":      "Security",
    "main":          "Application Entry Points",
    "unknown":       "Unclassified",
}

# Architectural layer each role belongs to
ROLE_LAYER: Dict[str, str] = {
    "controller":    "Presentation",
    "service":       "Business",
    "repository":    "Persistence",
    "entity":        "Data Model",
    "dto":           "Data Transfer",
    "configuration": "Configuration",
    "component":     "Business",
    "security":      "Security",
    "exception":     "Cross-cutting",
    "utility":       "Cross-cutting",
    "main":          "Bootstrap",
    "unknown":       "Unknown",
}


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class ClassRole:
    """Architectural role of a single Java class."""
    class_name: str
    package: str
    file_path: str
    role: str
    confidence: str          # high | medium | low
    detection_method: str    # annotation | interface | naming | package | unknown
    annotations: List[str]
    methods: List[str]
    interfaces: List[str]

    @property
    def fully_qualified(self) -> str:
        return f"{self.package}.{self.class_name}" if self.package else self.class_name

    @property
    def layer(self) -> str:
        return ROLE_LAYER.get(self.role, "Unknown")

    def to_dict(self) -> dict:
        return {
            "class_name":       self.class_name,
            "package":          self.package,
            "file_path":        self.file_path,
            "role":             self.role,
            "layer":            self.layer,
            "confidence":       self.confidence,
            "detection_method": self.detection_method,
            "annotations":      self.annotations,
        }


# ---------------------------------------------------------------------------
# Core detection logic
# ---------------------------------------------------------------------------

def _detect_role(
    class_name: str,
    package: str,
    annotations: List[str],
    interfaces: List[str],
    methods: List[str],
) -> Tuple[str, str, str]:
    """Return (role, confidence, detection_method)."""

    # 1. Annotation-based -- most reliable
    for ann in annotations:
        if ann in ANNOTATION_ROLES:
            role, conf = ANNOTATION_ROLES[ann]
            return role, conf, "annotation"

    # 2. Interface-based -- extends JpaRepository etc.
    for iface in interfaces:
        base = iface.split("<")[0].strip()
        if base in REPO_INTERFACES:
            return "repository", "high", "interface"

    # 3. Naming suffix -- sorted by descending length to match longest first
    for suffix, role in sorted(SUFFIX_ROLES.items(), key=lambda x: -len(x[0])):
        if class_name.endswith(suffix) and len(class_name) > len(suffix):
            return role, "medium", "naming"

    # 4. Package segment hint
    if package:
        for segment in reversed(package.split(".")):
            hint = PACKAGE_HINTS.get(segment.lower())
            if hint:
                return hint, "low", "package"

    return "unknown", "low", "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_all_roles(metadata: List[dict]) -> List[ClassRole]:
    """
    Detect architectural roles for every class/interface in the metadata list.
    Returns one ClassRole per detected type declaration.
    """
    roles: List[ClassRole] = []
    seen: set = set()

    for entry in metadata:
        package    = entry.get("package") or ""
        file_path  = entry.get("file_path", "")
        annotations = entry.get("annotations") or []
        methods    = entry.get("methods") or []
        interfaces = entry.get("interfaces") or []

        all_types: List[str] = []
        all_types.extend(entry.get("classes") or [])
        all_types.extend(entry.get("interfaces") or [])

        for type_name in all_types:
            key = (package, type_name)
            if key in seen:
                continue
            seen.add(key)

            role, conf, method = _detect_role(
                type_name, package, annotations, interfaces, methods
            )
            roles.append(ClassRole(
                class_name=type_name,
                package=package,
                file_path=file_path,
                role=role,
                confidence=conf,
                detection_method=method,
                annotations=list(annotations),
                methods=list(methods),
                interfaces=list(interfaces),
            ))

    return roles


def group_by_role(roles: List[ClassRole]) -> Dict[str, List[ClassRole]]:
    """Group ClassRole objects by their role string."""
    groups: Dict[str, List[ClassRole]] = {}
    for r in roles:
        groups.setdefault(r.role, []).append(r)
    return groups


def group_by_layer(roles: List[ClassRole]) -> Dict[str, List[ClassRole]]:
    """Group ClassRole objects by their architectural layer."""
    groups: Dict[str, List[ClassRole]] = {}
    for r in roles:
        groups.setdefault(r.layer, []).append(r)
    return groups
