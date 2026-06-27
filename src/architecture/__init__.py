from __future__ import annotations

"""
Architecture Understanding Engine -- Phase 5.

Analyses package structure, layered architecture, Spring Boot patterns,
module boundaries, and generates Mermaid diagrams, C4 descriptions,
and onboarding documentation.

Quick start:
    from src.architecture import analyze_architecture
    from src.ingest import load_metadata

    report = analyze_architecture(load_metadata())
    print(report.summary())
"""

from typing import List, Optional

import networkx as nx

from src.architecture.detector import detect_all_roles, group_by_role
from src.architecture.analyzer import analyze, ArchitectureReport
from src.architecture.diagram import all_diagrams
from src.architecture.c4 import full_c4_model
from src.architecture.onboarding import generate_onboarding


def analyze_architecture(
    metadata: List[dict],
    graph: Optional[nx.DiGraph] = None,
) -> ArchitectureReport:
    """
    Full architecture analysis from ingested metadata.

    Args:
        metadata : list of file dicts from ingest.load_metadata()
        graph    : optional dependency graph from dependency.build_full_graph()

    Returns:
        ArchitectureReport with all analysis results.
    """
    return analyze(metadata, graph)
