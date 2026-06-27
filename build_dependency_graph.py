from __future__ import annotations

"""
Phase 4: Dependency Intelligence CLI.

Builds a dependency graph from an ingested Java repository,
runs analysis, answers sample queries, and exports results.

Prerequisites:
  1. python main.py          -- ingest a repository
  2. python build_vector_db.py  -- (optional, for RAG)
  3. python build_dependency_graph.py  -- this script

Outputs in data/:
  dependency_graph.json       -- node-link JSON (D3.js / Cytoscape.js)
  dependency_adjacency.json   -- simple {nodes, edges, stats} JSON
  dependency_graph.dot        -- Graphviz DOT file
  dependency_analysis.json    -- analysis report JSON
"""

import json
from pathlib import Path

from src.ingest import load_metadata
from src.dependency import build_full_graph, DependencyQueryEngine
from src.dependency.analyzer import analyze
from src.dependency.exporter import save_json, save_adjacency_json, save_dot


def _section(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def main() -> None:
    _section("Java Dependency Intelligence")

    print("\nLoading repository metadata...")
    metadata = load_metadata()
    print(f"  {len(metadata)} files loaded")

    print("\nExtracting dependencies and building graph...")
    G = build_full_graph(metadata)
    print(f"  Nodes (classes)       : {G.number_of_nodes()}")
    print(f"  Edges (dependencies)  : {G.number_of_edges()}")
    print(f"  Is DAG (no cycles)    : {__import__('networkx').is_directed_acyclic_graph(G)}")

    # ---- Analysis --------------------------------------------------------
    _section("Analysis Report")
    report = analyze(G)
    print(report.summary())

    # ---- Sample queries --------------------------------------------------
    _section("Sample Queries")

    engine = DependencyQueryEngine(G)

    print("\nGraph statistics:")
    stats = engine.graph_stats()
    for k, v in stats.items():
        print(f"  {k:<35}: {v}")

    print("\nMost depended-on classes:")
    for r in engine.most_depended_on(5):
        if r["dependents"] > 0:
            print(f"  {r['class']:<35} ({r['class_type']:<12}) "
                  f"depended on by {r['dependents']} class(es)")

    print("\nClasses with most outgoing dependencies:")
    for r in engine.most_dependencies(5):
        if r["dependencies"] > 0:
            print(f"  {r['class']:<35} ({r['class_type']:<12}) "
                  f"depends on {r['dependencies']} class(es)")

    # Dynamic query examples using actual nodes
    nodes = list(G.nodes)
    if len(nodes) >= 2:
        source = nodes[0]
        target = nodes[-1]
        print(f"\nDependency chain: {source} -> {target}")
        chain = engine.dependency_chain(source, target)
        print(f"  {engine.format_chain(chain)}")

        print(f"\nWho depends on '{target}'?")
        for r in engine.who_depends_on(target)[:5]:
            print(f"  {r['class']} ({r['relationship']}, {r['dep_type']})")

    # ---- Export ----------------------------------------------------------
    _section("Exporting")
    out = Path("data")
    save_json(G, out / "dependency_graph.json")
    save_adjacency_json(G, out / "dependency_adjacency.json")
    save_dot(G, out / "dependency_graph.dot")

    report_path = out / "dependency_analysis.json"
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2), encoding="utf-8"
    )
    print(f"  Analysis report -> {report_path}")

    print("\nDone. Run `dot -Tpng data/dependency_graph.dot -o dep.png` to visualise.")


if __name__ == "__main__":
    main()
