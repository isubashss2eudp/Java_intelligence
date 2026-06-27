from __future__ import annotations

"""
Architecture analyser -- builds structured reports from detected class roles.

Produces:
  - Package tree (nested package hierarchy)
  - Layer map (which classes belong to Presentation/Business/Persistence)
  - Module boundaries (top-level sub-packages treated as modules)
  - Spring Boot pattern summary (REST endpoints, JPA entities, etc.)
  - ArchitectureReport (consolidates everything)
"""

from dataclasses import dataclass, field
from collections import defaultdict
from typing import Any, Dict, List, Optional

import networkx as nx

from src.architecture.detector import (
    ClassRole,
    detect_all_roles,
    group_by_role,
    group_by_layer,
    ROLE_LABELS,
    ROLE_LAYER,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PackageNode:
    """One node in the package hierarchy tree."""
    name: str                          # full dotted package name
    simple_name: str                   # last segment
    classes: List[ClassRole] = field(default_factory=list)
    children: List["PackageNode"] = field(default_factory=list)

    @property
    def dominant_role(self) -> str:
        if not self.classes:
            return "unknown"
        counts: Dict[str, int] = defaultdict(int)
        for c in self.classes:
            counts[c.role] += 1
        return max(counts, key=lambda k: counts[k])

    @property
    def total_classes(self) -> int:
        return len(self.classes) + sum(c.total_classes for c in self.children)

    def to_dict(self) -> dict:
        return {
            "name":         self.name,
            "simple_name":  self.simple_name,
            "class_count":  len(self.classes),
            "dominant_role": self.dominant_role,
            "children":     [c.to_dict() for c in self.children],
        }


@dataclass
class ArchitectureLayer:
    """A horizontal layer in the application architecture."""
    name: str                          # e.g. "Presentation"
    roles: List[str]                   # which roles belong here
    classes: List[ClassRole] = field(default_factory=list)
    packages: List[str] = field(default_factory=list)
    inbound_deps: int = 0
    outbound_deps: int = 0

    @property
    def class_count(self) -> int:
        return len(self.classes)

    def to_dict(self) -> dict:
        return {
            "name":         self.name,
            "roles":        self.roles,
            "class_count":  self.class_count,
            "packages":     sorted(set(self.packages)),
            "inbound_deps":  self.inbound_deps,
            "outbound_deps": self.outbound_deps,
        }


@dataclass
class ModuleBoundary:
    """A sub-module identified by its root package segment."""
    name: str                          # module name (package segment)
    root_package: str                  # full root package e.g. com.demo.order
    classes: List[ClassRole] = field(default_factory=list)
    roles_present: List[str] = field(default_factory=list)
    is_full_stack: bool = False        # has controller + service + repo

    def to_dict(self) -> dict:
        return {
            "name":         self.name,
            "root_package": self.root_package,
            "class_count":  len(self.classes),
            "roles":        sorted(set(self.roles_present)),
            "is_full_stack": self.is_full_stack,
        }


@dataclass
class SpringBootPatterns:
    """Detected Spring Boot-specific patterns."""
    has_spring_boot_main: bool = False
    rest_controller_count: int = 0
    jpa_entity_count: int = 0
    spring_data_repo_count: int = 0
    has_security: bool = False
    has_scheduling: bool = False
    has_async: bool = False
    entry_point_class: str = ""
    base_package: str = ""
    patterns_detected: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "has_spring_boot_main":    self.has_spring_boot_main,
            "rest_controller_count":   self.rest_controller_count,
            "jpa_entity_count":        self.jpa_entity_count,
            "spring_data_repo_count":  self.spring_data_repo_count,
            "has_security":            self.has_security,
            "has_scheduling":          self.has_scheduling,
            "has_async":               self.has_async,
            "entry_point_class":       self.entry_point_class,
            "base_package":            self.base_package,
            "patterns_detected":       self.patterns_detected,
        }


@dataclass
class ArchitectureReport:
    """Consolidated architecture analysis result."""
    base_package: str
    roles_by_name: Dict[str, List[ClassRole]]
    roles_by_layer: Dict[str, List[ClassRole]]
    layers: List[ArchitectureLayer]
    modules: List[ModuleBoundary]
    package_tree: Optional[PackageNode]
    spring_patterns: SpringBootPatterns
    all_roles: List[ClassRole]
    stats: Dict[str, Any]

    def summary(self) -> str:
        sep = "-" * 60
        lines = [
            sep,
            "  Architecture Understanding Report",
            sep,
            f"  Base package         : {self.base_package or 'unknown'}",
            f"  Total classes        : {self.stats.get('total_classes', 0)}",
            f"  Detected roles       : {self.stats.get('detected_classes', 0)}",
            f"  Unclassified         : {self.stats.get('unknown_classes', 0)}",
            f"  Modules detected     : {len(self.modules)}",
            "",
            "  Layer Breakdown:",
        ]
        for layer in self.layers:
            if layer.class_count > 0:
                pkg_list = ", ".join(sorted(set(layer.packages))[:3])
                if len(set(layer.packages)) > 3:
                    pkg_list += "..."
                lines.append(
                    f"    {layer.name:<20} {layer.class_count:>3} class(es)  "
                    f"packages: {pkg_list}"
                )
        lines.append("")
        lines.append("  Role Distribution:")
        for role, classes in sorted(self.roles_by_name.items(),
                                     key=lambda x: -len(x[1])):
            if role != "unknown" and classes:
                label = ROLE_LABELS.get(role, role)
                lines.append(f"    {label:<25} {len(classes):>3}")
        if self.spring_patterns.patterns_detected:
            lines.append("")
            lines.append("  Spring Boot Patterns:")
            for p in self.spring_patterns.patterns_detected:
                lines.append(f"    + {p}")
        lines.append(sep)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "base_package":    self.base_package,
            "stats":           self.stats,
            "layers":          [l.to_dict() for l in self.layers],
            "modules":         [m.to_dict() for m in self.modules],
            "spring_patterns": self.spring_patterns.to_dict(),
            "roles": {
                role: [r.to_dict() for r in classes]
                for role, classes in self.roles_by_name.items()
            },
        }


# ---------------------------------------------------------------------------
# Package tree builder
# ---------------------------------------------------------------------------

def _find_base_package(metadata: List[dict]) -> str:
    """Infer the common root package from all metadata entries."""
    packages = [
        e.get("package") or ""
        for e in metadata
        if e.get("package")
    ]
    if not packages:
        return ""
    parts_list = [p.split(".") for p in packages]
    if not parts_list:
        return ""
    common = parts_list[0]
    for parts in parts_list[1:]:
        new_common = []
        for a, b in zip(common, parts):
            if a == b:
                new_common.append(a)
            else:
                break
        common = new_common
        if not common:
            break
    return ".".join(common)


def build_package_tree(roles: List[ClassRole]) -> Optional[PackageNode]:
    """Build a hierarchical package tree from detected class roles."""
    if not roles:
        return None

    packages: Dict[str, List[ClassRole]] = defaultdict(list)
    for role in roles:
        packages[role.package or "(default)"].append(role)

    # Find common root
    all_pkgs = [p for p in packages if p != "(default)"]
    if not all_pkgs:
        return PackageNode("(default)", "(default)", list(roles))

    # Build tree nodes bottom-up
    nodes: Dict[str, PackageNode] = {}
    for pkg, classes in packages.items():
        nodes[pkg] = PackageNode(
            name=pkg,
            simple_name=pkg.split(".")[-1],
            classes=classes,
        )

    # Wire up parent-child relationships
    root_pkg = _find_base_package(
        [{"package": p} for p in all_pkgs]
    )
    if not root_pkg:
        root_pkg = all_pkgs[0].split(".")[0]

    # Ensure root node exists
    if root_pkg not in nodes:
        nodes[root_pkg] = PackageNode(root_pkg, root_pkg.split(".")[-1])

    for pkg in sorted(nodes.keys()):
        if pkg == root_pkg:
            continue
        parts = pkg.split(".")
        for i in range(len(parts) - 1, 0, -1):
            parent_name = ".".join(parts[:i])
            if parent_name in nodes:
                if nodes[pkg] not in nodes[parent_name].children:
                    nodes[parent_name].children.append(nodes[pkg])
                break

    return nodes.get(root_pkg)


# ---------------------------------------------------------------------------
# Layer builder
# ---------------------------------------------------------------------------

_LAYER_DEFINITIONS = [
    ("Presentation",  ["controller"]),
    ("Business",      ["service", "component"]),
    ("Persistence",   ["repository"]),
    ("Data Model",    ["entity"]),
    ("Data Transfer", ["dto"]),
    ("Configuration", ["configuration"]),
    ("Security",      ["security"]),
    ("Cross-cutting", ["exception", "utility"]),
    ("Bootstrap",     ["main"]),
    ("Unknown",       ["unknown"]),
]


def build_layers(
    roles_by_name: Dict[str, List[ClassRole]],
    graph: Optional[nx.DiGraph] = None,
) -> List[ArchitectureLayer]:
    """Create ArchitectureLayer objects and optionally annotate with dep counts."""
    layers = []
    for layer_name, role_names in _LAYER_DEFINITIONS:
        classes = []
        for role in role_names:
            classes.extend(roles_by_name.get(role, []))
        if not classes:
            continue
        pkgs = list({c.package for c in classes if c.package})
        layer = ArchitectureLayer(
            name=layer_name,
            roles=role_names,
            classes=classes,
            packages=pkgs,
        )
        if graph:
            layer_nodes = {c.class_name for c in classes}
            in_count = sum(
                1 for _, t in graph.edges()
                if t in layer_nodes
                and graph.nodes.get(_, {}).get("class_type") not in
                {r for r in role_names}
            )
            out_count = sum(
                1 for s, _ in graph.edges()
                if s in layer_nodes
            )
            layer.inbound_deps = in_count
            layer.outbound_deps = out_count
        layers.append(layer)
    return layers


# ---------------------------------------------------------------------------
# Module detector
# ---------------------------------------------------------------------------

def detect_modules(roles: List[ClassRole], base_package: str) -> List[ModuleBoundary]:
    """
    Detect module boundaries by grouping classes under the first sub-package
    segment after the base_package.

    e.g. com.demo.order.service.OrderService -> module 'order'
    """
    if not base_package:
        return []

    module_map: Dict[str, List[ClassRole]] = defaultdict(list)
    base_depth = len(base_package.split("."))

    for role in roles:
        pkg = role.package or ""
        parts = pkg.split(".")
        if len(parts) > base_depth and pkg.startswith(base_package):
            module_name = parts[base_depth]
            module_map[module_name].append(role)

    modules = []
    for name, classes in sorted(module_map.items()):
        roles_present = list({c.role for c in classes})
        full_stack = (
            any(c.role == "controller" for c in classes) and
            any(c.role == "service" for c in classes) and
            any(c.role == "repository" for c in classes)
        )
        modules.append(ModuleBoundary(
            name=name,
            root_package=f"{base_package}.{name}",
            classes=classes,
            roles_present=roles_present,
            is_full_stack=full_stack,
        ))
    return modules


# ---------------------------------------------------------------------------
# Spring Boot pattern detector
# ---------------------------------------------------------------------------

def detect_spring_patterns(
    roles_by_name: Dict[str, List[ClassRole]],
    all_roles: List[ClassRole],
) -> SpringBootPatterns:
    """Detect Spring Boot-specific architectural patterns."""
    patterns = SpringBootPatterns()

    main_classes = roles_by_name.get("main", [])
    if main_classes:
        patterns.has_spring_boot_main = True
        patterns.entry_point_class = main_classes[0].class_name
        if main_classes[0].package:
            patterns.base_package = main_classes[0].package
        patterns.patterns_detected.append(
            f"Spring Boot application: {main_classes[0].class_name}"
        )

    controllers = roles_by_name.get("controller", [])
    rest_count = sum(
        1 for c in controllers
        if "RestController" in c.annotations or "RequestMapping" in c.annotations
    )
    patterns.rest_controller_count = rest_count
    if rest_count:
        patterns.patterns_detected.append(
            f"REST API: {rest_count} REST controller(s)"
        )

    entities = roles_by_name.get("entity", [])
    patterns.jpa_entity_count = len(entities)
    if entities:
        patterns.patterns_detected.append(
            f"JPA/ORM: {len(entities)} entity class(es)"
        )

    repos = roles_by_name.get("repository", [])
    spring_data = sum(
        1 for c in repos
        if c.detection_method == "interface" or "Repository" in c.annotations
    )
    patterns.spring_data_repo_count = spring_data
    if spring_data:
        patterns.patterns_detected.append(
            f"Spring Data: {spring_data} repository/repositories"
        )

    security_classes = roles_by_name.get("security", [])
    has_security_ann = any(
        ann in ("EnableWebSecurity", "PreAuthorize", "Secured")
        for r in all_roles
        for ann in r.annotations
    )
    if security_classes or has_security_ann:
        patterns.has_security = True
        patterns.patterns_detected.append("Spring Security configured")

    has_sched = any(
        "Scheduled" in r.annotations for r in all_roles
    )
    if has_sched:
        patterns.has_scheduling = True
        patterns.patterns_detected.append("Scheduled tasks (@Scheduled)")

    has_async = any(
        "Async" in r.annotations or "EnableAsync" in r.annotations
        for r in all_roles
    )
    if has_async:
        patterns.has_async = True
        patterns.patterns_detected.append("Async processing (@Async)")

    dtos = roles_by_name.get("dto", [])
    if dtos:
        patterns.patterns_detected.append(
            f"DTO pattern: {len(dtos)} transfer object(s)"
        )

    return patterns


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------

def analyze(
    metadata: List[dict],
    graph: Optional[nx.DiGraph] = None,
) -> ArchitectureReport:
    """
    Run full architecture analysis on ingested metadata.

    Args:
        metadata : list of file metadata dicts
        graph    : optional NetworkX dependency graph

    Returns:
        ArchitectureReport
    """
    all_roles = detect_all_roles(metadata)
    roles_by_name = group_by_role(all_roles)
    roles_by_layer = group_by_layer(all_roles)

    base_package = _find_base_package(metadata)
    package_tree = build_package_tree(all_roles)
    layers = build_layers(roles_by_name, graph)
    modules = detect_modules(all_roles, base_package)
    spring = detect_spring_patterns(roles_by_name, all_roles)

    if spring.base_package:
        base_package = spring.base_package

    total = len(all_roles)
    unknown = len(roles_by_name.get("unknown", []))
    stats = {
        "total_classes":     total,
        "detected_classes":  total - unknown,
        "unknown_classes":   unknown,
        "detection_rate":    round((total - unknown) / total, 3) if total else 0.0,
        "layer_count":       len(layers),
        "module_count":      len(modules),
        "role_count":        len(roles_by_name),
    }

    return ArchitectureReport(
        base_package=base_package,
        roles_by_name=roles_by_name,
        roles_by_layer=roles_by_layer,
        layers=layers,
        modules=modules,
        package_tree=package_tree,
        spring_patterns=spring,
        all_roles=all_roles,
        stats=stats,
    )
