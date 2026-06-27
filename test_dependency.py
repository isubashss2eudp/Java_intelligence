from __future__ import annotations

"""
Test suite for the Dependency Intelligence module.

Tests cover:
  - Extractor: import, field injection, constructor injection
  - Graph builder: nodes, edges, dedup, known-only filter
  - Analyzer: circular deps, orphans, coupling, layer violations
  - Query engine: all named queries
  - Exporter: JSON and DOT output validity

All tests use in-memory Java source -- no file I/O during extraction tests.
Integration tests use the sample_spring_repo/ fixture directory.
"""

import json
import tempfile
from pathlib import Path

import networkx as nx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_source(*lines: str) -> bytes:
    return "\n".join(lines).encode("utf-8")


# ---------------------------------------------------------------------------
# 1. Extractor tests
# ---------------------------------------------------------------------------

def test_import_extraction():
    src = make_source(
        "package com.demo.service;",
        "import com.demo.repository.CustomerRepository;",
        "import com.demo.service.EmailService;",
        "import java.util.List;",
        "@Service public class OrderService {",
        "  public void run() {}",
        "}",
    )
    from src.dependency.extractor import extract_dependencies
    results = extract_dependencies(src, "OrderService.java")
    assert len(results) == 1, f"Expected 1 class, got {len(results)}"
    cls = results[0]
    assert cls.class_name == "OrderService"
    assert cls.package == "com.demo.service"
    assert cls.class_type == "service"
    targets = {e.target for e in cls.edges}
    assert "CustomerRepository" in targets, f"Expected CustomerRepository in {targets}"
    assert "EmailService" in targets
    assert "List" not in targets, "java.util.List should not create an edge"
    print("  [OK] import extraction")


def test_field_injection_extraction():
    src = make_source(
        "package com.demo.service;",
        "import com.demo.repository.CustomerRepository;",
        "@Service public class CustomerService {",
        "  @Autowired",
        "  private CustomerRepository customerRepo;",
        "  public String get() { return null; }",
        "}",
    )
    from src.dependency.extractor import extract_dependencies
    results = extract_dependencies(src, "CustomerService.java")
    cls = results[0]
    field_edges = [e for e in cls.edges if e.dep_type == "field_injection"]
    assert len(field_edges) == 1, f"Expected 1 field_injection, got {field_edges}"
    assert field_edges[0].target == "CustomerRepository"
    print("  [OK] field injection extraction")


def test_constructor_injection_extraction():
    src = make_source(
        "package com.demo.service;",
        "import com.demo.repository.OrderRepository;",
        "import com.demo.repository.CustomerRepository;",
        "@Service public class OrderService {",
        "  private final OrderRepository orderRepo;",
        "  private final CustomerRepository customerRepo;",
        "  public OrderService(OrderRepository orderRepo, CustomerRepository customerRepo) {",
        "    this.orderRepo = orderRepo;",
        "    this.customerRepo = customerRepo;",
        "  }",
        "}",
    )
    from src.dependency.extractor import extract_dependencies
    results = extract_dependencies(src, "OrderService.java")
    cls = results[0]
    ctor_edges = {e.target: e for e in cls.edges if e.dep_type == "constructor_injection"}
    assert "OrderRepository" in ctor_edges, f"Missing OrderRepository in {list(ctor_edges)}"
    assert "CustomerRepository" in ctor_edges
    print("  [OK] constructor injection extraction")


def test_dedup_favours_injection_over_import():
    """When both import and field_injection exist, keep field_injection."""
    src = make_source(
        "package com.demo.service;",
        "import com.demo.repository.CustomerRepository;",
        "@Service public class Svc {",
        "  @Autowired private CustomerRepository repo;",
        "}",
    )
    from src.dependency.extractor import extract_dependencies
    results = extract_dependencies(src, "Svc.java")
    edges = results[0].edges
    repo_edges = [e for e in edges if e.target == "CustomerRepository"]
    assert len(repo_edges) == 1
    assert repo_edges[0].dep_type == "field_injection", (
        f"Expected field_injection, got {repo_edges[0].dep_type}"
    )
    print("  [OK] dedup favours field_injection over import")


# ---------------------------------------------------------------------------
# 2. Graph builder tests
# ---------------------------------------------------------------------------

def _make_two_class_deps():
    from src.dependency.extractor import ClassDependencies, DependencyEdge
    edge = DependencyEdge(
        source="OrderService", target="CustomerRepository",
        dep_type="field_injection", source_file="f.java", line=5
    )
    return [
        ClassDependencies("OrderService", "com.demo.service", "OrderService.java",
                          "service", ["Service"], [edge]),
        ClassDependencies("CustomerRepository", "com.demo.repository",
                          "CustomerRepository.java", "repository", ["Repository"], []),
    ]


def test_graph_nodes_and_edges():
    from src.dependency.graph import build_dependency_graph
    G = build_dependency_graph(_make_two_class_deps())
    assert "OrderService" in G.nodes
    assert "CustomerRepository" in G.nodes
    assert G.has_edge("OrderService", "CustomerRepository")
    assert G["OrderService"]["CustomerRepository"]["dep_type"] == "field_injection"
    print("  [OK] graph nodes and edges")


def test_graph_filters_unknown_targets():
    """Edges to classes not in the node set must be dropped."""
    from src.dependency.extractor import ClassDependencies, DependencyEdge
    from src.dependency.graph import build_dependency_graph
    edge = DependencyEdge("A", "UnknownExternal", "import", "A.java", 1)
    deps = [ClassDependencies("A", "com", "A.java", "service", [], [edge])]
    G = build_dependency_graph(deps)
    assert G.number_of_edges() == 0, "External class should not create an edge"
    print("  [OK] graph filters unknown targets")


# ---------------------------------------------------------------------------
# 3. Analyzer tests
# ---------------------------------------------------------------------------

def _make_cycle_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    for node, ctype in [("A", "service"), ("B", "service"), ("C", "service"),
                         ("Orphan", "unknown")]:
        G.add_node(node, class_type=ctype, package="com", annotations=[],
                   file_path="", color="")
    G.add_edge("A", "B", dep_type="field_injection", source_file="", line=0)
    G.add_edge("B", "C", dep_type="field_injection", source_file="", line=0)
    G.add_edge("C", "A", dep_type="field_injection", source_file="", line=0)  # cycle
    return G


def test_detect_circular_dependencies():
    from src.dependency.analyzer import detect_circular_dependencies
    G = _make_cycle_graph()
    cycles = detect_circular_dependencies(G)
    assert len(cycles) >= 1
    cycle_nodes = {frozenset(c.cycle) for c in cycles}
    assert frozenset({"A", "B", "C"}) in cycle_nodes
    print("  [OK] circular dependency detection")


def test_detect_orphan_classes():
    from src.dependency.analyzer import detect_orphan_classes
    G = _make_cycle_graph()
    orphans = detect_orphan_classes(G)
    assert "Orphan" in orphans
    assert "A" not in orphans
    print("  [OK] orphan class detection")


def test_coupling_metrics():
    from src.dependency.analyzer import compute_coupling_metrics
    G = nx.DiGraph()
    for n, ct in [("Ctrl", "controller"), ("Svc", "service"), ("Repo", "repository")]:
        G.add_node(n, class_type=ct, package="", annotations=[], file_path="", color="")
    G.add_edge("Ctrl", "Svc",  dep_type="field_injection", source_file="", line=0)
    G.add_edge("Svc",  "Repo", dep_type="field_injection", source_file="", line=0)

    metrics = {m.class_name: m for m in compute_coupling_metrics(G)}
    assert metrics["Repo"].afferent_coupling == 1    # Svc depends on Repo
    assert metrics["Repo"].efferent_coupling == 0
    assert metrics["Ctrl"].efferent_coupling == 1
    assert metrics["Svc"].afferent_coupling  == 1
    assert metrics["Svc"].efferent_coupling  == 1
    print("  [OK] coupling metrics")


def test_layer_violation_detection():
    from src.dependency.analyzer import detect_layer_violations
    G = nx.DiGraph()
    for n, ct in [("Repo", "repository"), ("Svc", "service"), ("Ctrl", "controller")]:
        G.add_node(n, class_type=ct, package="", annotations=[], file_path="", color="")
    # Violation: Repo (rank 1) -> Svc (rank 2)
    G.add_edge("Repo", "Svc", dep_type="field_injection", source_file="", line=0)
    # Valid: Ctrl -> Svc
    G.add_edge("Ctrl", "Svc", dep_type="field_injection", source_file="", line=0)

    violations = detect_layer_violations(G)
    assert ("Repo", "Svc") in violations
    assert ("Ctrl", "Svc") not in violations
    print("  [OK] layer violation detection")


# ---------------------------------------------------------------------------
# 4. Query engine tests
# ---------------------------------------------------------------------------

def _make_query_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    nodes = [
        ("OrderController", "controller"),
        ("OrderService",    "service"),
        ("CustomerService", "service"),
        ("OrderRepository", "repository"),
        ("CustomerRepository", "repository"),
    ]
    for name, ctype in nodes:
        G.add_node(name, class_type=ctype, package="com.demo", annotations=[],
                   file_path="", color="")
    edges = [
        ("OrderController",  "OrderService",       "field_injection"),
        ("OrderService",     "OrderRepository",    "constructor_injection"),
        ("OrderService",     "CustomerRepository", "constructor_injection"),
        ("CustomerService",  "CustomerRepository", "field_injection"),
    ]
    for src, tgt, dt in edges:
        G.add_edge(src, tgt, dep_type=dt, source_file="", line=0)
    return G


def test_who_depends_on():
    from src.dependency.queries import DependencyQueryEngine
    engine = DependencyQueryEngine(_make_query_graph())
    result = engine.who_depends_on("CustomerRepository")
    classes = {r["class"] for r in result}
    assert "OrderService" in classes
    assert "CustomerService" in classes
    # OrderController is transitive via OrderService
    assert "OrderController" in classes
    print("  [OK] who_depends_on")


def test_dependency_chain():
    from src.dependency.queries import DependencyQueryEngine
    engine = DependencyQueryEngine(_make_query_graph())
    chain = engine.dependency_chain("OrderController", "CustomerRepository")
    assert chain is not None
    names = [step["class"] for step in chain]
    assert names[0] == "OrderController"
    assert names[-1] == "CustomerRepository"
    print("  [OK] dependency_chain")


def test_no_path_returns_none():
    from src.dependency.queries import DependencyQueryEngine
    engine = DependencyQueryEngine(_make_query_graph())
    chain = engine.dependency_chain("OrderRepository", "OrderController")
    assert chain is None
    print("  [OK] no-path returns None")


def test_classes_by_type():
    from src.dependency.queries import DependencyQueryEngine
    engine = DependencyQueryEngine(_make_query_graph())
    repos = engine.classes_by_type("repository")
    assert set(repos) == {"OrderRepository", "CustomerRepository"}
    print("  [OK] classes_by_type")


def test_most_depended_on():
    from src.dependency.queries import DependencyQueryEngine
    engine = DependencyQueryEngine(_make_query_graph())
    top = engine.most_depended_on(3)
    # CustomerRepository has 2 dependents
    assert top[0]["class"] == "CustomerRepository"
    assert top[0]["dependents"] == 2
    print("  [OK] most_depended_on")


# ---------------------------------------------------------------------------
# 5. Exporter tests
# ---------------------------------------------------------------------------

def test_json_export_roundtrip():
    from src.dependency.exporter import to_node_link_json, to_adjacency_json
    G = _make_query_graph()
    nld = to_node_link_json(G)
    adj = to_adjacency_json(G)

    assert "nodes" in nld
    assert "links" in nld
    assert "nodes" in adj
    assert "edges" in adj
    assert adj["stats"]["total_classes"] == G.number_of_nodes()
    assert adj["stats"]["total_dependencies"] == G.number_of_edges()

    # Must be JSON-serialisable
    json.dumps(nld)
    json.dumps(adj)
    print("  [OK] JSON export round-trip")


def test_dot_export():
    from src.dependency.exporter import to_dot
    G = _make_query_graph()
    dot = to_dot(G)
    assert "digraph" in dot
    assert "OrderController" in dot
    assert "CustomerRepository" in dot
    print("  [OK] DOT export")


def test_save_json_creates_file():
    from src.dependency.exporter import save_json
    G = _make_query_graph()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "graph.json"
        save_json(G, path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert "nodes" in data
    print("  [OK] save_json creates file")


# ---------------------------------------------------------------------------
# 6. Integration test -- sample Spring Boot repo
# ---------------------------------------------------------------------------

def test_integration_sample_spring_repo():
    """End-to-end: extract -> graph -> analyze -> query on sample_spring_repo/."""
    sample = Path(__file__).parent / "sample_spring_repo"
    if not sample.exists():
        print("  [SKIP] sample_spring_repo not found")
        return

    from src.dependency.extractor import extract_from_file
    from src.dependency.graph import build_dependency_graph
    from src.dependency.analyzer import analyze
    from src.dependency.queries import DependencyQueryEngine

    all_deps = []
    for jf in sample.glob("*.java"):
        all_deps.extend(extract_from_file(jf))

    G = build_dependency_graph(all_deps)
    assert G.number_of_nodes() > 5, f"Expected >5 nodes, got {G.number_of_nodes()}"
    assert G.number_of_edges() > 5, f"Expected >5 edges, got {G.number_of_edges()}"

    report = analyze(G)

    # NotificationService <-> AlertService is a circular dependency
    cycle_nodes = {frozenset(c.cycle) for c in report.circular_dependencies}
    assert any(
        "NotificationService" in s and "AlertService" in s
        for s in cycle_nodes
    ), f"Expected circular dep, found: {cycle_nodes}"

    # HealthCheckUtil has no connections -> orphan
    assert "HealthCheckUtil" in report.orphan_classes, (
        f"HealthCheckUtil should be orphan, orphans={report.orphan_classes}"
    )

    engine = DependencyQueryEngine(G)

    # CustomerRepository is used by OrderService AND CustomerService
    dependents = {r["class"] for r in engine.who_depends_on("CustomerRepository")}
    assert "OrderService" in dependents
    assert "CustomerService" in dependents

    # Chain: OrderController -> ... -> CustomerRepository
    chain = engine.dependency_chain("OrderController", "CustomerRepository")
    assert chain is not None
    path_classes = [s["class"] for s in chain]
    assert path_classes[0] == "OrderController"
    assert path_classes[-1] == "CustomerRepository"

    print(f"  [OK] integration: {G.number_of_nodes()} nodes, "
          f"{G.number_of_edges()} edges, "
          f"{len(report.circular_dependencies)} cycle(s), "
          f"{len(report.orphan_classes)} orphan(s)")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        # Extractor
        test_import_extraction,
        test_field_injection_extraction,
        test_constructor_injection_extraction,
        test_dedup_favours_injection_over_import,
        # Graph
        test_graph_nodes_and_edges,
        test_graph_filters_unknown_targets,
        # Analyzer
        test_detect_circular_dependencies,
        test_detect_orphan_classes,
        test_coupling_metrics,
        test_layer_violation_detection,
        # Queries
        test_who_depends_on,
        test_dependency_chain,
        test_no_path_returns_none,
        test_classes_by_type,
        test_most_depended_on,
        # Exporter
        test_json_export_roundtrip,
        test_dot_export,
        test_save_json_creates_file,
        # Integration
        test_integration_sample_spring_repo,
    ]

    sep = "-" * 60
    print(f"\n{sep}")
    print("  Dependency Intelligence Test Suite")
    print(sep)

    passed = failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {test.__name__}: {exc}")
            failed += 1

    print(sep)
    print(f"  Results: {passed} passed, {failed} failed")
    print(sep)

    if failed:
        raise SystemExit(1)
