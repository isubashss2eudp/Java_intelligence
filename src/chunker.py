"""
Semantic chunker for Java source files.

Strategy
--------
For each file we produce two tiers of chunks:

  1. CLASS-LEVEL chunk - package + imports + full class skeleton (method
     signatures without bodies).  This chunk answers "what is this class /
     what is its API surface?" questions.

  2. METHOD-LEVEL chunks - package + class header + one complete method body
     per chunk.  Each chunk is self-contained and fits comfortably inside an
     embedding model context window (=1500 chars by default).

Fallback: files with no parseable class structure are split with
RecursiveCharacterTextSplitter so they are never silently dropped.

All chunks carry rich metadata so the retriever can filter by package,
class, annotation, or method name without a full scan.
"""

from __future__ import annotations

from pathlib import Path

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
# -- tree-sitter singleton ----------------------------------------------------
_JAVA_LANGUAGE = Language(tsjava.language())
_TS_PARSER = Parser(_JAVA_LANGUAGE)

# Fallback splitter for non-class content (XML, YAML, etc.)
_FALLBACK_SPLITTER = RecursiveCharacterTextSplitter(
    separators=["\n\n", "\n", " "],
    chunk_size=1500,
    chunk_overlap=200,
)

# Maximum characters per method chunk before we fall back to plain splitting
MAX_METHOD_CHARS = 3000


# -- helpers ------------------------------------------------------------------

def _node_text(node) -> str:
    return node.text.decode("utf-8", errors="replace") if node.text else ""


def _collect_nodes(node, target_types: set) -> list:
    results = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur.type in target_types:
            results.append(cur)
        stack.extend(reversed(cur.children))
    return results


def _annotation_names(modifiers_node) -> list[str]:
    ann_types = {"marker_annotation", "annotation"}
    names = []
    for child in modifiers_node.children:
        if child.type in ann_types:
            for part in child.children:
                if part.type == "identifier":
                    names.append(_node_text(part))
                    break
    return names


def _build_class_header(class_node) -> str:
    """Return everything up to (but not including) the class body open brace."""
    parts = []
    for child in class_node.children:
        if child.type == "class_body":
            break
        parts.append(_node_text(child))
    return " ".join(p for p in parts if p.strip())


def _build_method_signature(method_node) -> str:
    """Return method signature (everything before the block body)."""
    sig_parts = []
    for child in method_node.children:
        if child.type == "block":
            break
        sig_parts.append(_node_text(child))
    return " ".join(p for p in sig_parts if p.strip())


def _build_prefix(package: str | None, imports: list[str],
                   class_header: str, annotations: list[str]) -> str:
    lines = []
    if package:
        lines.append(f"// package: {package}")
    if annotations:
        lines.append(f"// class annotations: {', '.join(annotations)}")
    lines.append(f"// {class_header}")
    lines.append("")
    return "\n".join(lines)


# -- per-file chunking --------------------------------------------------------

def _chunk_java_file(file_data: dict) -> list[Document]:
    """
    Produce all Document chunks for a single Java file.
    Reads raw content from disk using file_path (not from metadata).
    """
    file_path = file_data["file_path"]
    package = file_data.get("package") or ""
    annotations_meta = file_data.get("annotations") or []

    # Read content from disk - not stored in metadata
    try:
        raw = Path(file_path).read_bytes()
        source = raw.decode("utf-8", errors="replace")
    except OSError:
        return []

    tree = _TS_PARSER.parse(raw)
    root = tree.root_node

    class_nodes = _collect_nodes(
        root,
        {"class_declaration", "interface_declaration",
         "enum_declaration", "record_declaration"}
    )

    if not class_nodes:
        # Fallback: split without class structure
        chunks = _FALLBACK_SPLITTER.split_text(source)
        return [
            Document(
                page_content=chunk,
                metadata={
                    "file": file_path,
                    "package": package,
                    "classes": "",
                    "annotations": ",".join(annotations_meta),
                    "chunk_type": "fallback",
                    "chunk_index": i,
                }
            )
            for i, chunk in enumerate(chunks)
        ]

    documents = []

    for class_node in class_nodes:
        name_field = class_node.child_by_field_name("name")
        class_name = _node_text(name_field) if name_field else "Unknown"

        # Collect class-level annotations
        class_annotations: list[str] = []
        for child in class_node.children:
            if child.type == "modifiers":
                class_annotations = _annotation_names(child)
                break

        class_header = _build_class_header(class_node)
        prefix = _build_prefix(package, [], class_header, class_annotations)

        base_meta = {
            "file": file_path,
            "package": package,
            "class": class_name,
            "annotations": ",".join(class_annotations),
        }

        # -- Tier 1: class-level summary chunk -------------------------------
        body_node = class_node.child_by_field_name("body")
        if body_node:
            method_signatures = []
            field_lines = []

            for member in body_node.children:
                if member.type in ("method_declaration",
                                    "constructor_declaration"):
                    sig = _build_method_signature(member)
                    if sig:
                        method_signatures.append(f"    {sig};")
                elif member.type == "field_declaration":
                    field_lines.append(f"    {_node_text(member)}")

            summary_body = "\n".join(field_lines + method_signatures)
            class_summary = f"{prefix}{class_header} {{\n{summary_body}\n}}"

            documents.append(Document(
                page_content=class_summary,
                metadata={**base_meta, "chunk_type": "class_summary",
                           "chunk_index": 0}
            ))

            # -- Tier 2: per-method chunks ------------------------------------
            method_nodes = [
                m for m in body_node.children
                if m.type in ("method_declaration",
                               "constructor_declaration")
            ]

            for idx, method_node in enumerate(method_nodes, 1):
                method_name_node = method_node.child_by_field_name("name")
                method_name = (_node_text(method_name_node)
                               if method_name_node else "unknown")

                method_anns: list[str] = []
                for child in method_node.children:
                    if child.type == "modifiers":
                        method_anns = _annotation_names(child)
                        break

                method_text = _node_text(method_node)

                # If a single method is enormous, split it further
                if len(method_text) > MAX_METHOD_CHARS:
                    sub_chunks = _FALLBACK_SPLITTER.split_text(method_text)
                    for sub_idx, sub in enumerate(sub_chunks):
                        documents.append(Document(
                            page_content=prefix + sub,
                            metadata={
                                **base_meta,
                                "method": method_name,
                                "method_annotations": ",".join(method_anns),
                                "chunk_type": "method_part",
                                "chunk_index": idx * 1000 + sub_idx,
                            }
                        ))
                else:
                    documents.append(Document(
                        page_content=prefix + method_text,
                        metadata={
                            **base_meta,
                            "method": method_name,
                            "method_annotations": ",".join(method_anns),
                            "chunk_type": "method",
                            "chunk_index": idx,
                        }
                    ))

    return documents


# -- Public API ----------------------------------------------------------------

def build_documents(repository_data: list[dict]) -> list[Document]:
    """
    Build LangChain Documents from the list of file metadata dicts
    produced by the ingest pipeline.
    """
    documents: list[Document] = []

    for file_data in repository_data:
        docs = _chunk_java_file(file_data)
        documents.extend(docs)

    return documents
