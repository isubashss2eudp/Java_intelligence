from __future__ import annotations

"""
Dependency Intelligence module.

Quick start:
    from src.dependency import build_full_graph, DependencyQueryEngine
    from src.ingest import load_metadata

    G = build_full_graph(load_metadata())
    engine = DependencyQueryEngine(G)
    print(engine.who_depends_on("CustomerRepository"))
"""

from typing import List

import networkx as nx

from src.dependency.extractor import extract_from_metadata
from src.dependency.graph import build_dependency_graph
from src.dependency.analyzer import analyze, AnalysisReport
from src.dependency.queries import DependencyQueryEngine
from src.dependency.exporter import save_json, save_dot, to_adjacency_json


def build_full_graph(metadata: List[dict]) -> nx.DiGraph:
    """
    Build the complete dependency graph from ingested metadata.

    Args:
        metadata: List of file metadata dicts from ingest.load_metadata()

    Returns:
        NetworkX DiGraph -- nodes are class names, edges are dependency
        relationships annotated with dep_type, source_file, and line number.
    """
    class_deps = extract_from_metadata(metadata)
    return build_dependency_graph(class_deps)
