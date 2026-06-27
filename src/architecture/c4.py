from __future__ import annotations

"""
C4 model architecture descriptions.

Generates three levels of the C4 model as structured text:
  Level 1 -- System Context  (the app and external actors)
  Level 2 -- Container       (deployment units: app, DB, cache)
  Level 3 -- Component       (internal components per architectural layer)

Output format is C4-PlantUML-compatible DSL comments plus prose descriptions
suitable for documentation or LLM consumption.
"""

from typing import Dict, List

from src.architecture.analyzer import ArchitectureReport
from src.architecture.detector import ROLE_LABELS


# ---------------------------------------------------------------------------
# Level 1: System Context
# ---------------------------------------------------------------------------

def system_context(report: ArchitectureReport, app_name: str = "") -> str:
    """
    C4 Level 1: System Context description.
    Describes the application and its external actors.
    """
    if not app_name:
        main_classes = report.roles_by_name.get("main", [])
        if main_classes:
            app_name = main_classes[0].class_name.replace("Application", "")
        else:
            app_name = report.base_package.split(".")[-1].title() if report.base_package else "Application"

    controllers = report.roles_by_name.get("controller", [])
    repos = report.roles_by_name.get("repository", [])
    has_jpa = report.spring_patterns.jpa_entity_count > 0

    external_systems = []
    if has_jpa or repos:
        external_systems.append("Relational Database (JPA/Hibernate)")
    if any("Mongo" in c.class_name or "mongo" in c.package.lower()
           for c in repos):
        external_systems.append("MongoDB")
    if any("Redis" in c.class_name for c in report.all_roles):
        external_systems.append("Redis Cache")
    if report.spring_patterns.has_scheduling:
        external_systems.append("Scheduled Job Scheduler")

    lines = [
        "=" * 60,
        "  C4 Model -- Level 1: System Context",
        "=" * 60,
        "",
        f"System: {app_name} Service",
        f"Base Package: {report.base_package or 'unknown'}",
        "",
        "Description:",
        f"  The {app_name} Service is a Spring Boot application that",
        f"  exposes {len(controllers)} REST endpoint group(s) and manages",
        f"  {report.stats.get('total_classes', 0)} Java classes across",
        f"  {report.stats.get('layer_count', 0)} architectural layers.",
        "",
        "External Actors:",
        "  [Person] End User / Client Application",
        "    -- Sends HTTP requests to REST controllers",
        "",
        "External Systems:",
    ]
    for sys in external_systems:
        lines.append(f"  [System] {sys}")
    if not external_systems:
        lines.append("  [System] Persistent Data Store (unspecified)")

    lines += [
        "",
        "Relationships:",
        f"  Client      --[HTTPS/JSON]-->  {app_name} Service",
    ]
    for sys in external_systems:
        lines.append(f"  {app_name} Service  --[data]-->  {sys}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Level 2: Container
# ---------------------------------------------------------------------------

def container_diagram(report: ArchitectureReport, app_name: str = "") -> str:
    """
    C4 Level 2: Container description.
    Shows the main deployment units.
    """
    if not app_name:
        main_classes = report.roles_by_name.get("main", [])
        app_name = (main_classes[0].class_name.replace("Application", "")
                    if main_classes else "App")

    controllers = report.roles_by_name.get("controller", [])
    services    = report.roles_by_name.get("service", [])
    repos       = report.roles_by_name.get("repository", [])

    lines = [
        "=" * 60,
        "  C4 Model -- Level 2: Container",
        "=" * 60,
        "",
        "Containers:",
        "",
        f"  [Container: Spring Boot Application]  {app_name}-service",
        f"    Technology : Java {{}}, Spring Boot",
        f"    Description: Main application container. Hosts",
        f"                 {len(controllers)} controller(s),",
        f"                 {len(services)} service(s),",
        f"                 {len(repos)} repository/repositories.",
        "",
    ]

    if report.spring_patterns.jpa_entity_count > 0:
        lines += [
            "  [Container: Database]  relational-db",
            "    Technology : PostgreSQL / MySQL / H2 (via JPA/Hibernate)",
            f"    Description: Persistent storage for",
            f"                 {report.spring_patterns.jpa_entity_count} entity type(s).",
            "",
        ]

    if any("Redis" in c.class_name for c in report.all_roles):
        lines += [
            "  [Container: Cache]  redis-cache",
            "    Technology : Redis",
            "    Description: Distributed cache layer.",
            "",
        ]

    lines += [
        "Container Relationships:",
        f"  Client        --[HTTPS/REST/JSON]-->  {app_name}-service",
        f"  {app_name}-service  --[JDBC/JPA]-->   relational-db",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Level 3: Component (per layer)
# ---------------------------------------------------------------------------

def component_diagram(
    report: ArchitectureReport,
    layer_name: str = "Business",
) -> str:
    """
    C4 Level 3: Component description for a specific layer.
    """
    layer = next(
        (l for l in report.layers if l.name == layer_name), None
    )
    if not layer:
        return f"Layer '{layer_name}' not found in report."

    lines = [
        "=" * 60,
        f"  C4 Model -- Level 3: Component ({layer_name} Layer)",
        "=" * 60,
        "",
        f"Layer: {layer_name}",
        f"Classes: {layer.class_count}",
        f"Packages: {', '.join(sorted(set(layer.packages))[:5])}",
        "",
        "Components:",
    ]

    for cls in sorted(layer.classes, key=lambda c: c.class_name):
        ann_str = (
            f" [@{', @'.join(cls.annotations[:3])}]"
            if cls.annotations else ""
        )
        method_count = len(cls.methods)
        lines.append(
            f"  [Component]  {cls.class_name}{ann_str}"
        )
        lines.append(
            f"               Package: {cls.package}"
        )
        lines.append(
            f"               Methods: {method_count}  "
            f"Detection: {cls.detection_method} ({cls.confidence})"
        )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Full C4 model
# ---------------------------------------------------------------------------

def full_c4_model(report: ArchitectureReport, app_name: str = "") -> str:
    """
    Generate all three C4 levels as a single document.
    """
    sections = [
        system_context(report, app_name),
        "",
        container_diagram(report, app_name),
        "",
    ]

    # Add component diagrams for main layers
    for layer_name in ("Presentation", "Business", "Persistence"):
        layer = next(
            (l for l in report.layers if l.name == layer_name and l.class_count > 0),
            None
        )
        if layer:
            sections.append(component_diagram(report, layer_name))
            sections.append("")

    return "\n".join(sections)
