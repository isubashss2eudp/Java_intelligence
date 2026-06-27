from __future__ import annotations

"""
NetworkX directed graph builder for Java class dependencies.

Graph schema
------------
Nodes  -- simple class names (str)
  Attributes: package, class_type, annotations, file_path, color

Edges  -- directed: source depends on target
  Attributes: dep_type, source_file, line
"""

from typing import List

import networkx as nx

from src.dependency.extractor import ClassDependencies, _EDGE_PRIORITY

# Visual colour by architectural layer (used by exporter)
NODE_COLORS = {
    "controller":    "#FF6B6B",
    "service":       "#4ECDC4",
    "repository":    "#45B7D1",
    "component":     "#96CEB4",
    "configuration": "#FFEAA7",
    "bean":          "#FFEAA7",
    "unknown":       "#DFE6E9",
}


def build_dependency_graph(class_deps: List[ClassDependencies]) -> nx.DiGraph:
    """
    Build a directed dependency graph from a list of ClassDependencies.

    Only edges whose target is a known class (present in the node set) are
    added -- external library classes (e.g. java.util.List) are ignored.
    """
    G = nx.DiGraph(name="java_dependency_graph")

    known = {cd.class_name for cd in class_deps}

    # Phase 1 -- add all nodes
    for cd in class_deps:
        G.add_node(
            cd.class_name,
            package=cd.package or "",
            class_type=cd.class_type,
            annotations=list(cd.annotations),
            file_path=cd.file_path,
            color=NODE_COLORS.get(cd.class_type, NODE_COLORS["unknown"]),
        )

    # Phase 2 -- add edges (internal dependencies only)
    for cd in class_deps:
        for edge in cd.edges:
            if edge.target not in known or edge.source == edge.target:
                continue

            if G.has_edge(edge.source, edge.target):
                # Upgrade to higher-priority dep_type if applicable
                cur = G[edge.source][edge.target].get("dep_type", "import")
                if _EDGE_PRIORITY.get(edge.dep_type, 0) > _EDGE_PRIORITY.get(cur, 0):
                    G[edge.source][edge.target].update(
                        dep_type=edge.dep_type, line=edge.line
                    )
            else:
                G.add_edge(
                    edge.source, edge.target,
                    dep_type=edge.dep_type,
                    source_file=edge.source_file,
                    line=edge.line,
                )

    return G
