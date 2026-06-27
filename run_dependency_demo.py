"""Ingest sample_spring_repo and run full dependency analysis."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.ingest import ingest_repository, save_metadata
from src.dependency import build_full_graph, DependencyQueryEngine
from src.dependency.analyzer import analyze
from src.dependency.exporter import save_json, save_adjacency_json, save_dot
import json

print("\n=== Ingesting sample_spring_repo ===")
data = ingest_repository("sample_spring_repo")
save_metadata(data)
print(f"  {len(data)} files ingested")

print("\n=== Building Dependency Graph ===")
G = build_full_graph(data)
print(f"  Nodes : {G.number_of_nodes()}")
print(f"  Edges : {G.number_of_edges()}")
print(f"  Is DAG: {__import__('networkx').is_directed_acyclic_graph(G)}")

print("\n=== Analysis Report ===")
report = analyze(G)
print(report.summary())

print("\n=== Sample Queries ===")
engine = DependencyQueryEngine(G)

print("\nQ: Which classes depend on CustomerRepository?")
for r in engine.who_depends_on("CustomerRepository"):
    print(f"  {r['class']:<30} ({r['class_type']:<12}) [{r['relationship']}, {r['dep_type']}]")

print("\nQ: What does OrderService depend on?")
for r in engine.get_dependencies("OrderService"):
    print(f"  {r['class']:<30} ({r['class_type']:<12}) [{r['relationship']}]")

print("\nQ: Dependency chain: OrderController -> CustomerRepository")
chain = engine.dependency_chain("OrderController", "CustomerRepository")
print(f"  {engine.format_chain(chain)}")

print("\nQ: All paths: OrderController -> CustomerRepository")
for path in engine.all_paths("OrderController", "CustomerRepository"):
    print(f"  {' -> '.join(path)}")

print("\nQ: Most depended-on classes (top 5)")
for r in engine.most_depended_on(5):
    if r["dependents"] > 0:
        print(f"  {r['class']:<30} depended on by {r['dependents']} class(es)")

print("\nQ: Classes by type")
for ctype in ["controller", "service", "repository", "configuration"]:
    classes = engine.classes_by_type(ctype)
    if classes:
        print(f"  {ctype:<15}: {', '.join(classes)}")

print("\n=== Exporting ===")
out = Path("data")
save_json(G, out / "dependency_graph.json")
save_adjacency_json(G, out / "dependency_adjacency.json")
save_dot(G, out / "dependency_graph.dot")
(out / "dependency_analysis.json").write_text(
    json.dumps(report.to_dict(), indent=2), encoding="utf-8"
)
print("  dependency_analysis.json saved")
print("\nAll done.")
