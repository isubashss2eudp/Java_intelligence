from __future__ import annotations

"""
Graph export utilities.

Formats:
  JSON (node-link)    -- compatible with D3.js, Cytoscape.js
  JSON (adjacency)    -- simpler {nodes, edges, stats} format
  DOT                 -- Graphviz; render with: dot -Tpng dep.dot -o dep.png
"""

import json
from pathlib import Path
from typing import Any, Dict

import networkx as nx
from networkx.readwrite import json_graph


# ---------------------------------------------------------------------------
# JSON exports
# ---------------------------------------------------------------------------

def to_node_link_json(G: nx.DiGraph) -> Dict[str, Any]:
    """
    NetworkX node-link format -- directly usable with D3.js force graphs
    and Cytoscape.js.
    """
    data = json_graph.node_link_data(G)
    # Ensure annotations list is serialisable
    for node in data.get("nodes", []):
        if isinstance(node.get("annotations"), list):
            node["annotations"] = node["annotations"]
    return data


def to_adjacency_json(G: nx.DiGraph) -> Dict[str, Any]:
    """
    Simplified adjacency format:
    {
        "nodes": [...],
        "edges": [...],
        "stats": {...}
    }
    """
    nodes = [
        {
            "id":         node,
            "package":    data.get("package", ""),
            "class_type": data.get("class_type", ""),
            "annotations": data.get("annotations", []),
            "file_path":  data.get("file_path", ""),
        }
        for node, data in G.nodes(data=True)
    ]
    edges = [
        {
            "source":      src,
            "target":      tgt,
            "dep_type":    data.get("dep_type", ""),
            "line":        data.get("line", 0),
        }
        for src, tgt, data in G.edges(data=True)
    ]
    stats = {
        "total_classes":              G.number_of_nodes(),
        "total_dependencies":         G.number_of_edges(),
        "is_dag":                     nx.is_directed_acyclic_graph(G),
        "weakly_connected_components": nx.number_weakly_connected_components(G),
        "density":                    round(nx.density(G), 4),
    }
    return {"nodes": nodes, "edges": edges, "stats": stats}


def save_json(G: nx.DiGraph, path: Path) -> None:
    """Save the graph as node-link JSON (D3.js/Cytoscape compatible)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_node_link_json(G), f, indent=2, ensure_ascii=False)
    print(f"  Node-link JSON -> {path} ({path.stat().st_size // 1024} KB)")


def save_adjacency_json(G: nx.DiGraph, path: Path) -> None:
    """Save the graph as simplified adjacency JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_adjacency_json(G), f, indent=2, ensure_ascii=False)
    print(f"  Adjacency JSON  -> {path} ({path.stat().st_size // 1024} KB)")


# ---------------------------------------------------------------------------
# DOT (Graphviz) export
# ---------------------------------------------------------------------------

_DOT_FILL = {
    "controller":    "tomato",
    "service":       "lightblue",
    "repository":    "lightgreen",
    "component":     "lightyellow",
    "configuration": "plum",
    "bean":          "plum",
    "unknown":       "lightgray",
}

_DOT_EDGE_STYLE = {
    "constructor_injection": ("bold",   "darkblue"),
    "field_injection":       ("solid",  "steelblue"),
    "import":                ("dashed", "gray"),
}


def to_dot(G: nx.DiGraph) -> str:
    """Render graph as Graphviz DOT source."""
    lines = [
        "digraph java_dependencies {",
        '  rankdir="TB";',
        '  graph [fontname="Helvetica", fontsize=12];',
        '  node  [shape=box, style=filled, fontname="Helvetica", fontsize=10];',
        '  edge  [fontname="Helvetica", fontsize=8];',
        "",
    ]

    for node, data in G.nodes(data=True):
        pkg   = data.get("package", "")
        ctype = data.get("class_type", "unknown")
        fill  = _DOT_FILL.get(ctype, "lightgray")
        label = f"{node}\n[{ctype}]\n{pkg}" if pkg else f"{node}\n[{ctype}]"
        lines.append(f'  "{node}" [label="{label}", fillcolor="{fill}"];')

    lines.append("")

    for src, tgt, data in G.edges(data=True):
        dep_type = data.get("dep_type", "import")
        style, color = _DOT_EDGE_STYLE.get(dep_type, ("dashed", "gray"))
        lines.append(
            f'  "{src}" -> "{tgt}" '
            f'[style="{style}", color="{color}", label="{dep_type}"];'
        )

    lines.append("}")
    return chr(10).join(lines)


def save_dot(G: nx.DiGraph, path: Path) -> None:
    """Save Graphviz DOT file. Render: dot -Tpng dep.dot -o dep.png"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_dot(G), encoding="utf-8")
    print(f"  DOT graph       -> {path}")
    print(f"    Render with:  dot -Tpng {path} -o {path.with_suffix('.png')}")
