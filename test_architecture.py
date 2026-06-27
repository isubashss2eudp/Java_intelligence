from __future__ import annotations

"""
Test suite for the Architecture Understanding Engine (Phase 5).

Tests cover:
  - Detector: annotations, naming, package hints, interface-based
  - Analyzer: layers, modules, package tree, Spring patterns
  - Diagram: all five Mermaid diagram types
  - C4: system context, container, component, full model
  - Summarizer: template fallback (no LLM)
  - Onboarding: full document generation and structure
  - Integration: end-to-end on sample_spring_repo/
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_METADATA = [
    {
        "file_path": "sample/OrderController.java",
        "package": "com.demo.controller",
        "classes": ["OrderController"],
        "interfaces": [],
        "enums": [],
        "annotations": ["RestController", "RequestMapping"],
        "methods": ["getOrders", "createOrder"],
        "lines_of_code": 40,
        "content_hash": "abc1",
    },
    {
        "file_path": "sample/CustomerController.java",
        "package": "com.demo.controller",
        "classes": ["CustomerController"],
        "interfaces": [],
        "enums": [],
        "annotations": ["RestController"],
        "methods": ["getCustomers"],
        "lines_of_code": 25,
        "content_hash": "abc2",
    },
    {
        "file_path": "sample/OrderService.java",
        "package": "com.demo.service",
        "classes": ["OrderService"],
        "interfaces": [],
        "enums": [],
        "annotations": ["Service"],
        "methods": ["processOrder", "cancelOrder", "getOrderHistory"],
        "lines_of_code": 80,
        "content_hash": "abc3",
    },
    {
        "file_path": "sample/CustomerService.java",
        "package": "com.demo.service",
        "classes": ["CustomerService"],
        "interfaces": [],
        "enums": [],
        "annotations": ["Service"],
        "methods": ["findCustomer", "createCustomer"],
        "lines_of_code": 55,
        "content_hash": "abc4",
    },
    {
        "file_path": "sample/OrderRepository.java",
        "package": "com.demo.repository",
        "classes": [],
        "interfaces": ["OrderRepository"],
        "enums": [],
        "annotations": ["Repository"],
        "methods": ["findByUserId", "findByStatus"],
        "lines_of_code": 15,
        "content_hash": "abc5",
    },
    {
        "file_path": "sample/CustomerRepository.java",
        "package": "com.demo.repository",
        "classes": [],
        "interfaces": ["CustomerRepository"],
        "enums": [],
        "annotations": ["Repository"],
        "methods": ["findById", "findByEmail"],
        "lines_of_code": 12,
        "content_hash": "abc6",
    },
    {
        "file_path": "sample/Order.java",
        "package": "com.demo.entity",
        "classes": ["Order"],
        "interfaces": [],
        "enums": [],
        "annotations": ["Entity", "Table"],
        "methods": ["getId", "setId"],
        "lines_of_code": 60,
        "content_hash": "abc7",
    },
    {
        "file_path": "sample/Customer.java",
        "package": "com.demo.entity",
        "classes": ["Customer"],
        "interfaces": [],
        "enums": [],
        "annotations": ["Entity"],
        "methods": ["getId"],
        "lines_of_code": 50,
        "content_hash": "abc8",
    },
    {
        "file_path": "sample/OrderDTO.java",
        "package": "com.demo.dto",
        "classes": ["OrderDTO"],
        "interfaces": [],
        "enums": [],
        "annotations": [],
        "methods": ["getOrderId"],
        "lines_of_code": 30,
        "content_hash": "abc9",
    },
    {
        "file_path": "sample/AppConfig.java",
        "package": "com.demo.config",
        "classes": ["AppConfig"],
        "interfaces": [],
        "enums": [],
        "annotations": ["Configuration"],
        "methods": ["dataSource"],
        "lines_of_code": 35,
        "content_hash": "abc10",
    },
    {
        "file_path": "sample/DemoApplication.java",
        "package": "com.demo",
        "classes": ["DemoApplication"],
        "interfaces": [],
        "enums": [],
        "annotations": ["SpringBootApplication"],
        "methods": ["main"],
        "lines_of_code": 15,
        "content_hash": "abc11",
    },
]


def _make_report():
    from src.architecture.analyzer import analyze
    return analyze(SAMPLE_METADATA)


# ---------------------------------------------------------------------------
# 1. Detector tests
# ---------------------------------------------------------------------------

def test_annotation_detection_service():
    from src.architecture.detector import detect_all_roles
    roles = detect_all_roles(SAMPLE_METADATA)
    services = [r for r in roles if r.role == "service"]
    assert len(services) >= 2, f"Expected >=2 services, got {len(services)}"
    assert all(r.detection_method == "annotation" for r in services)
    assert all(r.confidence == "high" for r in services)
    print("  [OK] annotation detection: service")


def test_annotation_detection_controller():
    from src.architecture.detector import detect_all_roles
    roles = detect_all_roles(SAMPLE_METADATA)
    ctrl = [r for r in roles if r.role == "controller"]
    assert len(ctrl) >= 2
    print("  [OK] annotation detection: controller")


def test_annotation_detection_entity():
    from src.architecture.detector import detect_all_roles
    roles = detect_all_roles(SAMPLE_METADATA)
    entities = [r for r in roles if r.role == "entity"]
    assert len(entities) >= 2
    print("  [OK] annotation detection: entity")


def test_naming_suffix_dto():
    from src.architecture.detector import _detect_role
    role, conf, method = _detect_role("OrderDTO", "com.demo.dto", [], [], [])
    assert role == "dto", f"Expected dto, got {role}"
    assert method == "naming"
    print("  [OK] naming suffix detection: DTO")


def test_naming_suffix_config():
    from src.architecture.detector import _detect_role
    role, conf, method = _detect_role("DatabaseConfig", "com.demo", [], [], [])
    assert role == "configuration"
    print("  [OK] naming suffix detection: Config")


def test_package_hint_fallback():
    from src.architecture.detector import _detect_role
    # No annotations, no known suffix, but 'security' package hint
    role, conf, method = _detect_role("JwtFilter", "com.demo.security", [], [], [])
    assert role == "security"
    assert method == "package"
    print("  [OK] package hint fallback: security")


def test_spring_boot_main_detection():
    from src.architecture.detector import detect_all_roles
    roles = detect_all_roles(SAMPLE_METADATA)
    main_classes = [r for r in roles if r.role == "main"]
    assert len(main_classes) >= 1
    assert main_classes[0].class_name == "DemoApplication"
    print("  [OK] SpringBootApplication detection")


def test_group_by_role():
    from src.architecture.detector import detect_all_roles, group_by_role
    roles = detect_all_roles(SAMPLE_METADATA)
    groups = group_by_role(roles)
    assert "service" in groups
    assert "controller" in groups
    assert "repository" in groups
    print("  [OK] group_by_role")


# ---------------------------------------------------------------------------
# 2. Analyzer tests
# ---------------------------------------------------------------------------

def test_base_package_detection():
    report = _make_report()
    assert report.base_package == "com.demo", (
        f"Expected com.demo, got {report.base_package}"
    )
    print("  [OK] base package detection")


def test_layers_populated():
    report = _make_report()
    layer_names = {l.name for l in report.layers}
    assert "Presentation" in layer_names
    assert "Business" in layer_names
    assert "Persistence" in layer_names
    assert "Data Model" in layer_names
    print("  [OK] layers populated")


def test_layer_class_counts():
    report = _make_report()
    layers = {l.name: l for l in report.layers}
    assert layers["Presentation"].class_count >= 2
    assert layers["Business"].class_count >= 2
    assert layers["Persistence"].class_count >= 2
    assert layers["Data Model"].class_count >= 2
    print("  [OK] layer class counts")


def test_stats():
    report = _make_report()
    assert report.stats["total_classes"] >= 10
    assert report.stats["detection_rate"] > 0.7
    print("  [OK] stats")


def test_spring_patterns():
    report = _make_report()
    sp = report.spring_patterns
    assert sp.has_spring_boot_main
    assert sp.entry_point_class == "DemoApplication"
    assert sp.jpa_entity_count >= 2
    assert sp.rest_controller_count >= 2
    print("  [OK] Spring Boot patterns")


def test_package_tree():
    report = _make_report()
    tree = report.package_tree
    assert tree is not None
    assert "com" in tree.name or "demo" in tree.name
    print("  [OK] package tree built")


def test_report_to_dict():
    report = _make_report()
    d = report.to_dict()
    assert "layers" in d
    assert "stats" in d
    assert "roles" in d
    assert "spring_patterns" in d
    # Must be JSON serialisable
    json.dumps(d)
    print("  [OK] report.to_dict() JSON serialisable")


# ---------------------------------------------------------------------------
# 3. Diagram tests
# ---------------------------------------------------------------------------

def test_layer_diagram():
    from src.architecture.diagram import layer_diagram
    report = _make_report()
    mmd = layer_diagram(report)
    assert "graph TB" in mmd
    assert "Presentation" in mmd or "Business" in mmd
    print("  [OK] layer_diagram Mermaid")


def test_package_diagram():
    from src.architecture.diagram import package_diagram
    report = _make_report()
    mmd = package_diagram(report)
    assert "graph LR" in mmd
    print("  [OK] package_diagram Mermaid")


def test_component_pie():
    from src.architecture.diagram import component_pie
    report = _make_report()
    mmd = component_pie(report)
    assert "pie" in mmd
    assert "Controllers" in mmd or "Services" in mmd
    print("  [OK] component_pie Mermaid")


def test_request_flow():
    from src.architecture.diagram import request_flow
    report = _make_report()
    mmd = request_flow(report)
    assert "sequenceDiagram" in mmd
    assert "HTTP Request" in mmd
    print("  [OK] request_flow sequence diagram")


def test_dependency_flow():
    from src.architecture.diagram import dependency_flow
    report = _make_report()
    mmd = dependency_flow(report)
    assert "flowchart" in mmd
    print("  [OK] dependency_flow flowchart")


def test_all_diagrams_returns_five():
    from src.architecture.diagram import all_diagrams
    report = _make_report()
    diagrams = all_diagrams(report)
    assert len(diagrams) == 5
    for key in ("layer_diagram", "package_diagram", "component_pie",
                "request_flow", "dependency_flow"):
        assert key in diagrams, f"Missing diagram: {key}"
    print("  [OK] all_diagrams returns 5 diagrams")


# ---------------------------------------------------------------------------
# 4. C4 tests
# ---------------------------------------------------------------------------

def test_system_context():
    from src.architecture.c4 import system_context
    report = _make_report()
    txt = system_context(report, "Demo")
    assert "System Context" in txt
    assert "Demo" in txt
    assert "REST" in txt or "controller" in txt.lower() or "HTTP" in txt
    print("  [OK] C4 system context")


def test_container_diagram():
    from src.architecture.c4 import container_diagram
    report = _make_report()
    txt = container_diagram(report, "Demo")
    assert "Container" in txt
    assert "Spring Boot" in txt
    print("  [OK] C4 container diagram")


def test_component_diagram():
    from src.architecture.c4 import component_diagram
    report = _make_report()
    txt = component_diagram(report, "Business")
    assert "Component" in txt
    assert "Business" in txt
    print("  [OK] C4 component diagram")


def test_full_c4_model():
    from src.architecture.c4 import full_c4_model
    report = _make_report()
    txt = full_c4_model(report, "Demo")
    assert "Level 1" in txt
    assert "Level 2" in txt
    assert "Level 3" in txt
    print("  [OK] full C4 model (3 levels)")


# ---------------------------------------------------------------------------
# 5. Summarizer tests
# ---------------------------------------------------------------------------

def test_template_summaries_no_llm():
    from src.architecture.summarizer import summarize_architecture
    report = _make_report()
    summaries = summarize_architecture(report, llm=None)
    assert "layer_summary" in summaries
    assert "module_summary" in summaries
    assert "spring_patterns" in summaries
    assert "onboarding_intro" in summaries
    assert "quick_start" in summaries
    assert "critique" in summaries
    for key, val in summaries.items():
        assert isinstance(val, str) and len(val) > 10, (
            f"Summary '{key}' is too short: {repr(val)}"
        )
    print("  [OK] template summaries (no LLM)")


def test_onboarding_document_structure():
    from src.architecture.summarizer import summarize_architecture
    from src.architecture.onboarding import generate_onboarding
    report = _make_report()
    summaries = summarize_architecture(report)
    doc = generate_onboarding(report, summaries, "Demo")

    assert "# Demo" in doc
    assert "Table of Contents" in doc
    assert "Package Structure" in doc
    assert "Layered Architecture" in doc
    assert "Spring Boot Patterns" in doc
    assert "Quick Start Guide" in doc
    assert "```mermaid" in doc
    assert len(doc.splitlines()) > 50
    print(f"  [OK] onboarding document ({len(doc.splitlines())} lines)")


# ---------------------------------------------------------------------------
# 6. Integration -- sample_spring_repo
# ---------------------------------------------------------------------------

def test_integration_sample_spring_repo():
    sample = ROOT / "sample_spring_repo"
    if not sample.exists():
        print("  [SKIP] sample_spring_repo not found")
        return

    from src.ingest import ingest_repository
    from src.architecture import analyze_architecture
    from src.architecture.diagram import all_diagrams
    from src.architecture.c4 import full_c4_model
    from src.architecture.summarizer import summarize_architecture
    from src.architecture.onboarding import generate_onboarding

    metadata = ingest_repository(str(sample))
    assert len(metadata) >= 10

    report = analyze_architecture(metadata)
    assert report.stats["total_classes"] >= 10
    assert report.stats["detection_rate"] > 0.7

    # Check key roles detected
    assert len(report.roles_by_name.get("service", [])) >= 3
    assert len(report.roles_by_name.get("repository", [])) >= 3
    assert len(report.roles_by_name.get("controller", [])) >= 1

    diagrams = all_diagrams(report)
    assert len(diagrams) == 5

    c4 = full_c4_model(report)
    assert "System Context" in c4

    summaries = summarize_architecture(report)
    assert "layer_summary" in summaries

    doc = generate_onboarding(report, summaries)
    assert "```mermaid" in doc
    assert len(doc.splitlines()) > 60

    print(
        f"  [OK] integration: {report.stats['total_classes']} classes, "
        f"{len(report.layers)} layers, "
        f"{len(diagrams)} diagrams, "
        f"{len(doc.splitlines())} doc lines"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        # Detector
        test_annotation_detection_service,
        test_annotation_detection_controller,
        test_annotation_detection_entity,
        test_naming_suffix_dto,
        test_naming_suffix_config,
        test_package_hint_fallback,
        test_spring_boot_main_detection,
        test_group_by_role,
        # Analyzer
        test_base_package_detection,
        test_layers_populated,
        test_layer_class_counts,
        test_stats,
        test_spring_patterns,
        test_package_tree,
        test_report_to_dict,
        # Diagram
        test_layer_diagram,
        test_package_diagram,
        test_component_pie,
        test_request_flow,
        test_dependency_flow,
        test_all_diagrams_returns_five,
        # C4
        test_system_context,
        test_container_diagram,
        test_component_diagram,
        test_full_c4_model,
        # Summarizer / Onboarding
        test_template_summaries_no_llm,
        test_onboarding_document_structure,
        # Integration
        test_integration_sample_spring_repo,
    ]

    sep = "-" * 60
    print(f"\n{sep}")
    print("  Architecture Understanding Engine -- Test Suite")
    print(sep)

    passed = failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as exc:
            import traceback
            print(f"  [FAIL] {test.__name__}: {exc}")
            traceback.print_exc()
            failed += 1

    print(sep)
    print(f"  Results: {passed} passed, {failed} failed")
    print(sep)

    if failed:
        raise SystemExit(1)
