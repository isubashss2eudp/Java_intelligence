from __future__ import annotations

"""
Mermaid diagram generator for Java architecture reports.

Produces five diagram types:
  layer_diagram    -- graph TB showing architectural layers and classes
  package_diagram  -- graph LR showing package hierarchy
  component_pie    -- pie chart of role distribution
  request_flow     -- sequenceDiagram for a typical HTTP request
  dependency_flow  -- flowchart showing data flow through layers
"""

from typing import Dict, List

from src.architecture.analyzer import ArchitectureReport, ArchitectureLayer
from src.architecture.detector import ROLE_LABELS, ClassRole

# Mermaid-safe colours per layer
_LAYER_COLOURS = {
    "Presentation":  "#FF6B6B",
    "Business":      "#4ECDC4",
    "Persistence":   "#45B7D1",
    "Data Model":    "#96CEB4",
    "Data Transfer": "#FFEAA7",
    "Configuration": "#DDA0DD",
    "Security":      "#F4A460",
    "Cross-cutting": "#D3D3D3",
    "Bootstrap":     "#98FB98",
}

_LAYER_STYLE = {
    "Presentation":  "fill:#FF6B6B,stroke:#cc0000,color:#fff",
    "Business":      "fill:#4ECDC4,stroke:#009688,color:#fff",
    "Persistence":   "fill:#45B7D1,stroke:#0288d1,color:#fff",
    "Data Model":    "fill:#96CEB4,stroke:#388e3c,color:#000",
    "Data Transfer": "fill:#FFEAA7,stroke:#f9a825,color:#000",
    "Configuration": "fill:#DDA0DD,stroke:#7b1fa2,color:#000",
    "Security":      "fill:#F4A460,stroke:#e65100,color:#000",
    "Cross-cutting": "fill:#D3D3D3,stroke:#616161,color:#000",
    "Bootstrap":     "fill:#98FB98,stroke:#2e7d32,color:#000",
}


def _safe_id(name: str) -> str:
    """Make a name safe for use as a Mermaid node ID."""
    return name.replace("-", "_").replace(".", "_").replace(" ", "_")


# ---------------------------------------------------------------------------
# 1. Layer Architecture Diagram
# ---------------------------------------------------------------------------

def layer_diagram(report: ArchitectureReport) -> str:
    """
    Mermaid graph showing classes grouped into architectural layers.
    """
    lines = [
        "graph TB",
        "    %% Architectural Layer Diagram",
    ]

    visible_layers = [l for l in report.layers if l.class_count > 0
                      and l.name not in ("Unknown", "Bootstrap")]

    style_lines = []
    for layer in visible_layers:
        safe_layer = _safe_id(layer.name)
        class_nodes = []
        for cls in layer.classes[:12]:   # cap at 12 per layer for readability
            node_id = _safe_id(cls.class_name)
            class_nodes.append(f"        {node_id}[{cls.class_name}]")
            colour = _LAYER_STYLE.get(layer.name, "fill:#eee,stroke:#999")
            style_lines.append(f"    style {node_id} {colour}")

        if class_nodes:
            extra = ""
            if len(layer.classes) > 12:
                extra = f"\n        more{safe_layer}[...{len(layer.classes) - 12} more]"
            lines.append(
                f"    subgraph {safe_layer}[\"{layer.name} Layer "
                f"({layer.class_count} classes)\"]"
            )
            lines.extend(class_nodes)
            if extra:
                lines.append(extra)
            lines.append("    end")

    # Layer dependency arrows (Presentation -> Business -> Persistence)
    layer_order = ["Presentation", "Business", "Persistence"]
    for i in range(len(layer_order) - 1):
        src = _safe_id(layer_order[i])
        tgt = _safe_id(layer_order[i + 1])
        if (any(l.name == layer_order[i] for l in visible_layers) and
                any(l.name == layer_order[i + 1] for l in visible_layers)):
            lines.append(f"    {src} --> {tgt}")

    lines.extend(style_lines)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. Package Structure Diagram
# ---------------------------------------------------------------------------

def package_diagram(report: ArchitectureReport) -> str:
    """
    Mermaid graph showing the package hierarchy.
    """
    lines = [
        "graph LR",
        "    %% Package Structure Diagram",
    ]

    from src.architecture.detector import PACKAGE_HINTS

    # Group classes by package
    pkg_map: Dict[str, List[ClassRole]] = {}
    for cls in report.all_roles:
        pkg = cls.package or "(default)"
        pkg_map.setdefault(pkg, []).append(cls)

    # Show only packages that have at least one class
    base = report.base_package
    base_id = _safe_id(base or "root")

    if base:
        lines.append(f'    {base_id}["{base}"]')

    seen_edges = set()
    for pkg in sorted(pkg_map.keys()):
        count = len(pkg_map[pkg])
        dominant = max(
            set(c.role for c in pkg_map[pkg]),
            key=lambda r: sum(1 for c in pkg_map[pkg] if c.role == r)
        )
        label = ROLE_LABELS.get(dominant, dominant)
        pkg_id = _safe_id(pkg)
        simple = pkg.split(".")[-1]
        lines.append(f'    {pkg_id}["{simple} ({label}, {count})"]')

        if base and pkg != base and pkg.startswith(base):
            parts = pkg[len(base):].strip(".").split(".")
            if parts:
                if len(parts) == 1:
                    edge = (base_id, pkg_id)
                    if edge not in seen_edges:
                        lines.append(f"    {base_id} --> {pkg_id}")
                        seen_edges.add(edge)
                else:
                    parent_pkg = base + "." + ".".join(parts[:-1])
                    parent_id = _safe_id(parent_pkg)
                    edge = (parent_id, pkg_id)
                    if edge not in seen_edges:
                        lines.append(f"    {parent_id} --> {pkg_id}")
                        seen_edges.add(edge)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. Component Distribution Pie
# ---------------------------------------------------------------------------

def component_pie(report: ArchitectureReport) -> str:
    """
    Mermaid pie chart of role distribution.
    """
    lines = [
        'pie title Architecture Component Distribution',
    ]
    for role, classes in sorted(
        report.roles_by_name.items(), key=lambda x: -len(x[1])
    ):
        if role == "unknown" or not classes:
            continue
        label = ROLE_LABELS.get(role, role)
        lines.append(f'    "{label}" : {len(classes)}')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4. Request Flow Sequence Diagram
# ---------------------------------------------------------------------------

def request_flow(report: ArchitectureReport) -> str:
    """
    Mermaid sequence diagram showing a typical HTTP request through the layers.
    """
    # Pick representative class names from each layer
    controllers = report.roles_by_name.get("controller", [])
    services    = report.roles_by_name.get("service", [])
    repos       = report.roles_by_name.get("repository", [])
    entities    = report.roles_by_name.get("entity", [])

    ctrl_name = controllers[0].class_name if controllers else "Controller"
    svc_name  = services[0].class_name    if services    else "Service"
    repo_name = repos[0].class_name       if repos       else "Repository"

    lines = [
        "sequenceDiagram",
        "    autonumber",
        "    participant Client",
        f"    participant {ctrl_name}",
        f"    participant {svc_name}",
        f"    participant {repo_name}",
        "    participant Database",
        "",
        f"    Client->>{ctrl_name}: HTTP Request",
        f"    {ctrl_name}->>{ctrl_name}: Validate input / map DTO",
        f"    {ctrl_name}->>{svc_name}: Call business method",
        f"    {svc_name}->>{svc_name}: Apply business rules",
        f"    {svc_name}->>{repo_name}: Query data",
        f"    {repo_name}->>Database: SQL / NoSQL query",
        f"    Database-->>{repo_name}: Result set",
        f"    {repo_name}-->>{svc_name}: Entity / domain object",
        f"    {svc_name}-->>{ctrl_name}: DTO / response object",
        f"    {ctrl_name}->>Client: HTTP Response (JSON)",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5. Dependency Flow Diagram
# ---------------------------------------------------------------------------

def dependency_flow(report: ArchitectureReport) -> str:
    """
    Mermaid flowchart showing data flow through the architectural layers.
    """
    lines = [
        "flowchart TD",
        "    %% Dependency Flow Diagram",
        "",
        "    Client([HTTP Client])",
        "",
    ]

    layer_nodes: Dict[str, str] = {}
    visible = [l for l in report.layers
               if l.class_count > 0 and l.name not in ("Unknown", "Bootstrap")]

    for layer in visible:
        lid = _safe_id(layer.name)
        class_list = ", ".join(c.class_name for c in layer.classes[:4])
        if len(layer.classes) > 4:
            class_list += f" +{len(layer.classes) - 4} more"
        lines.append(
            f"    {lid}[\"{layer.name}\\n{class_list}\"]"
        )
        layer_nodes[layer.name] = lid

    lines.append("")

    # Client -> Presentation
    if "Presentation" in layer_nodes:
        lines.append(f"    Client -->|HTTP| {layer_nodes['Presentation']}")

    # Standard flow arrows
    flow = [
        ("Presentation", "Business",  "delegates to"),
        ("Business",     "Persistence","queries"),
        ("Persistence",  "Data Model", "maps to"),
        ("Business",     "Data Transfer", "returns"),
    ]
    for src, tgt, label in flow:
        if src in layer_nodes and tgt in layer_nodes:
            lines.append(
                f"    {layer_nodes[src]} -->|\"{label}\"| {layer_nodes[tgt]}"
            )

    # Style
    for layer_name, node_id in layer_nodes.items():
        style = _LAYER_STYLE.get(layer_name, "fill:#eee,stroke:#999")
        lines.append(f"    style {node_id} {style}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# All diagrams
# ---------------------------------------------------------------------------

def all_diagrams(report: ArchitectureReport) -> Dict[str, str]:
    """
    Generate all five Mermaid diagrams.

    Returns dict of {diagram_name -> mermaid_source}.
    """
    return {
        "layer_diagram":    layer_diagram(report),
        "package_diagram":  package_diagram(report),
        "component_pie":    component_pie(report),
        "request_flow":     request_flow(report),
        "dependency_flow":  dependency_flow(report),
    }
