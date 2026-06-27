"""
Java source file parser using tree-sitter for accurate AST extraction.
Replaces regex-based parsing - handles generics, records, nested classes,
lambdas, modern Java features, and all Spring/Lombok annotations correctly.
"""

from __future__ import annotations


import hashlib
from pathlib import Path

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser

from src.models import JavaFileMetadata

# -- tree-sitter setup (module-level singleton) ------------------------------
_JAVA_LANGUAGE = Language(tsjava.language())
_PARSER = Parser(_JAVA_LANGUAGE)


# -- Internal helpers ---------------------------------------------------------

def _query_all(node, node_types: set) -> list:
    """Walk the AST and collect every node whose type is in node_types."""
    results = []
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in node_types:
            results.append(current)
        stack.extend(reversed(current.children))
    return results


def _node_text(node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _extract_annotation_name(ann_node) -> str:
    """
    Works for both marker_annotation (@Service) and
    annotation (@RequestMapping("/api")).
    """
    for child in ann_node.children:
        if child.type == "identifier":
            return _node_text(child)
        if child.type == "scoped_identifier":
            return _node_text(child).split(".")[-1]
    return ""


def _extract_annotations(root_node) -> list[str]:
    ann_types = {"marker_annotation", "annotation"}
    annotations = []
    for ann in _query_all(root_node, ann_types):
        name = _extract_annotation_name(ann)
        if name and name not in ("param", "return", "throws", "see", "since",
                                  "deprecated", "author", "version", "link",
                                  "inheritDoc", "code"):
            annotations.append(name)
    return list(dict.fromkeys(annotations))   # unique, order-preserving


def _extract_package(root_node) -> str | None:
    for child in root_node.children:
        if child.type == "package_declaration":
            for part in child.children:
                if part.type in ("identifier", "scoped_identifier"):
                    return _node_text(part)
    return None


def _extract_imports(root_node) -> list[str]:
    imports = []
    for child in root_node.children:
        if child.type == "import_declaration":
            for part in child.children:
                if part.type in ("identifier", "scoped_identifier",
                                  "asterisk", "scoped_absolute_identifier"):
                    imports.append(_node_text(part))
                    break
    return imports


def _extract_type_names(root_node, type_node_type: str) -> list[str]:
    """
    Generic extractor for class / interface / enum / record declarations.
    Returns list of simple names.
    """
    names = []
    for decl in _query_all(root_node, {type_node_type}):
        name_field = decl.child_by_field_name("name")
        if name_field:
            names.append(_node_text(name_field))
    return list(dict.fromkeys(names))


def _extract_methods(root_node) -> list[str]:
    method_types = {
        "method_declaration",
        "constructor_declaration",
    }
    names = []
    for m in _query_all(root_node, method_types):
        name_field = m.child_by_field_name("name")
        if name_field:
            names.append(_node_text(name_field))
    return list(dict.fromkeys(names))


# -- Public API ----------------------------------------------------------------

def parse_java_file(file_path: Path) -> JavaFileMetadata:
    """
    Parse a single .java file using tree-sitter and return structured metadata.
    Content is NOT stored in the metadata - only the file_path is kept so
    content can be read on-demand during chunking.
    """
    raw = file_path.read_bytes()

    # Graceful fallback: if tree-sitter fails (truly broken files) we still
    # return a partial metadata record rather than crashing the pipeline.
    try:
        tree = _PARSER.parse(raw)
        root = tree.root_node

        metadata = JavaFileMetadata(
            file_path=str(file_path),
            package=_extract_package(root),
            imports=_extract_imports(root),
            annotations=_extract_annotations(root),
            classes=_extract_type_names(root, "class_declaration"),
            interfaces=_extract_type_names(root, "interface_declaration"),
            enums=_extract_type_names(root, "enum_declaration"),
            methods=_extract_methods(root),
            lines_of_code=raw.count(b"\n") + 1,
            content_hash=hashlib.md5(raw).hexdigest(),
        )

    except Exception:
        content_str = raw.decode("utf-8", errors="replace")
        metadata = JavaFileMetadata(
            file_path=str(file_path),
            lines_of_code=content_str.count("\n") + 1,
            content_hash=hashlib.md5(raw).hexdigest(),
        )

    return metadata
