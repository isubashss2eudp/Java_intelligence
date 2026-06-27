from __future__ import annotations

"""
Java dependency extractor using tree-sitter AST.

Extracts three classes of dependency relationship from each .java file:

  import          -- explicit import declarations
                     import com.demo.repo.CustomerRepository;
                     -> OrderService --[import]--> CustomerRepository

  field_injection -- @Autowired / @Inject / @Resource field declarations
                     @Autowired private CustomerRepository repo;
                     -> OrderService --[field_injection]--> CustomerRepository

  constructor_injection -- typed constructor parameters (Spring idiom)
                     public OrderService(CustomerRepository repo) { ... }
                     -> OrderService --[constructor_injection]--> CustomerRepository

When multiple edge types are found for the same (source, target) pair,
the edge is kept under the highest-priority type:
  constructor_injection > field_injection > import
"""

from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Dict, List, Optional

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser

_JAVA = Language(tsjava.language())
_PARSER = Parser(_JAVA)

INJECTION_ANNOTATIONS = frozenset({
    "Autowired", "Inject", "Resource", "Value", "Qualifier",
})

# Import prefixes that are never internal project classes
STD_LIB_PREFIXES = frozenset({
    "java.", "javax.", "jakarta.", "sun.", "com.sun.",
    "org.springframework.", "org.junit.", "org.slf4j.",
    "org.apache.", "com.fasterxml.", "io.micrometer.",
    "org.hibernate.", "org.aspectj.", "reactor.",
    "kotlin.", "scala.", "groovy.",
})


def _is_stdlib_import(qualified: str) -> bool:
    return any(qualified.startswith(prefix) for prefix in STD_LIB_PREFIXES)


COMPONENT_ANNOTATION_TO_TYPE: Dict[str, str] = {
    "Service": "service",
    "RestController": "controller",
    "Controller": "controller",
    "RequestMapping": "controller",
    "Repository": "repository",
    "Component": "component",
    "Configuration": "configuration",
    "Bean": "bean",
    "Singleton": "service",
    "Named": "component",
}

_EDGE_PRIORITY = {"constructor_injection": 3, "field_injection": 2, "import": 1}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DependencyEdge:
    """A directed dependency between two Java classes."""
    source: str
    target: str
    dep_type: str       # import | field_injection | constructor_injection
    source_file: str
    line: int = 0

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "dep_type": self.dep_type,
            "source_file": self.source_file,
            "line": self.line,
        }


@dataclass
class ClassDependencies:
    """All dependency information extracted from a single Java class."""
    class_name: str
    package: Optional[str]
    file_path: str
    class_type: str
    annotations: List[str]
    edges: List[DependencyEdge] = dc_field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "class_name": self.class_name,
            "package": self.package,
            "file_path": self.file_path,
            "class_type": self.class_type,
            "annotations": self.annotations,
            "edges": [e.to_dict() for e in self.edges],
        }


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _text(node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _annotation_name(ann_node) -> str:
    for child in ann_node.children:
        if child.type == "identifier":
            return _text(child)
        if child.type == "scoped_identifier":
            return _text(child).split(".")[-1]
    return ""


def _collect_modifiers_annotations(modifiers_node) -> List[str]:
    names = []
    for child in modifiers_node.children:
        if child.type in ("marker_annotation", "annotation"):
            name = _annotation_name(child)
            if name:
                names.append(name)
    return names


def _class_type(annotations: List[str]) -> str:
    for ann in annotations:
        if ann in COMPONENT_ANNOTATION_TO_TYPE:
            return COMPONENT_ANNOTATION_TO_TYPE[ann]
    return "unknown"


def _extract_package(root) -> Optional[str]:
    for child in root.children:
        if child.type == "package_declaration":
            for part in child.children:
                if part.type in ("identifier", "scoped_identifier"):
                    return _text(part)
    return None


# ---------------------------------------------------------------------------
# Edge extractors
# ---------------------------------------------------------------------------

# Qualified import prefixes that are never internal project classes
_STD_LIB_PREFIXES = (
    "java.", "javax.", "jakarta.", "sun.", "com.sun.",
    "org.springframework.", "org.junit.", "org.slf4j.",
    "org.apache.", "com.fasterxml.", "io.micrometer.",
    "org.hibernate.", "org.aspectj.", "reactor.",
    "kotlin.", "scala.", "groovy.",
)


def _is_stdlib_import(qualified: str) -> bool:
    return any(qualified.startswith(p) for p in _STD_LIB_PREFIXES)


def _import_edges(root, source: str, fp: str) -> List[DependencyEdge]:
    """One edge per import of a capitalised (class-name) identifier."""
    edges = []
    for child in root.children:
        if child.type != "import_declaration":
            continue
        line = child.start_point[0] + 1
        for part in child.children:
            if part.type in ("scoped_identifier", "identifier"):
                qualified = _text(part)
                # Skip standard library and well-known framework imports
                if _is_stdlib_import(qualified):
                    break
                # Walk from right to find first capitalised segment
                for seg in reversed(qualified.split(".")):
                    if seg and seg[0].isupper() and seg != source:
                        edges.append(DependencyEdge(
                            source=source, target=seg,
                            dep_type="import", source_file=fp, line=line,
                        ))
                    break
                break
    return edges


def _field_injection_edges(body, source: str, fp: str) -> List[DependencyEdge]:
    """@Autowired/@Inject field declarations."""
    edges = []
    for member in body.children:
        if member.type != "field_declaration":
            continue
        line = member.start_point[0] + 1
        injected = False
        type_name: Optional[str] = None

        for child in member.children:
            if child.type == "modifiers":
                for ann in child.children:
                    if ann.type in ("marker_annotation", "annotation"):
                        if _annotation_name(ann) in INJECTION_ANNOTATIONS:
                            injected = True

            elif child.type == "type_identifier":
                type_name = _text(child)

            elif child.type == "generic_type":
                # List<SomeType> / Optional<SomeType>
                for tc in child.children:
                    if tc.type == "type_arguments":
                        for ta in tc.children:
                            if ta.type == "type_identifier":
                                type_name = _text(ta)
                                break

        if injected and type_name and type_name[0].isupper() and type_name != source:
            edges.append(DependencyEdge(
                source=source, target=type_name,
                dep_type="field_injection", source_file=fp, line=line,
            ))
    return edges


def _constructor_injection_edges(body, source: str, fp: str) -> List[DependencyEdge]:
    """Typed constructor parameters (Spring constructor injection)."""
    edges = []
    for member in body.children:
        if member.type != "constructor_declaration":
            continue
        line = member.start_point[0] + 1
        params = member.child_by_field_name("parameters")
        if not params:
            continue
        for param in params.children:
            if param.type != "formal_parameter":
                continue
            for child in param.children:
                if child.type == "type_identifier":
                    t = _text(child)
                    if t and t[0].isupper() and t != source:
                        edges.append(DependencyEdge(
                            source=source, target=t,
                            dep_type="constructor_injection",
                            source_file=fp, line=line,
                        ))


    return edges


def _dedup_edges(edges: List[DependencyEdge]) -> List[DependencyEdge]:
    """Keep only the highest-priority edge per (source, target) pair."""
    best: Dict[tuple, DependencyEdge] = {}
    for e in edges:
        key = (e.source, e.target)
        existing = best.get(key)
        if (existing is None or
                _EDGE_PRIORITY.get(e.dep_type, 0) >
                _EDGE_PRIORITY.get(existing.dep_type, 0)):
            best[key] = e
    return list(best.values())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_TYPE_NODES = frozenset({
    "class_declaration", "interface_declaration",
    "enum_declaration", "record_declaration",
})


def _all_type_nodes(root):
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in _TYPE_NODES:
            yield node
        else:
            stack.extend(reversed(node.children))


def extract_dependencies(source: bytes, file_path: str) -> List[ClassDependencies]:
    """
    Parse Java source bytes with tree-sitter and return structured
    ClassDependencies for every class/interface/enum/record found.
    """
    tree = _PARSER.parse(source)
    root = tree.root_node
    package = _extract_package(root)
    results: List[ClassDependencies] = []

    for type_node in _all_type_nodes(root):
        name_field = type_node.child_by_field_name("name")
        if not name_field:
            continue
        class_name = _text(name_field)

        annotations: List[str] = []
        for child in type_node.children:
            if child.type == "modifiers":
                annotations = _collect_modifiers_annotations(child)
                break

        edges: List[DependencyEdge] = list(_import_edges(root, class_name, file_path))

        body = type_node.child_by_field_name("body")
        if body:
            edges.extend(_field_injection_edges(body, class_name, file_path))
            edges.extend(_constructor_injection_edges(body, class_name, file_path))

        results.append(ClassDependencies(
            class_name=class_name,
            package=package,
            file_path=file_path,
            class_type=_class_type(annotations),
            annotations=annotations,
            edges=_dedup_edges(edges),
        ))

    return results


def extract_from_file(file_path: Path) -> List[ClassDependencies]:
    """Parse a single .java file and return its ClassDependencies."""
    return extract_dependencies(file_path.read_bytes(), str(file_path))


def extract_from_metadata(metadata: List[dict]) -> List[ClassDependencies]:
    """
    Extract dependencies from the metadata list produced by ingest.py.
    Reads each source file from disk using the stored file_path.
    """
    results: List[ClassDependencies] = []
    for entry in metadata:
        fp = Path(entry["file_path"])
        if fp.exists():
            try:
                results.extend(extract_from_file(fp))
            except Exception as exc:
                print(f"  [WARN] Skipped {fp.name}: {exc}")
    return results
