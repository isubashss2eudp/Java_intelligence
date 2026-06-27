"""
Vector store management using ChromaDB.

Key improvements over v1:
- Named collection "java_repo" - prevents silent duplicates on re-runs.
- Documents are upserted by deterministic IDs derived from file path +
  chunk index, so re-indexing the same repo is idempotent.
- persist_directory resolved to an absolute path at import time so the
  store works regardless of the calling script working directory.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from langchain_core.documents import Document
from langchain_chroma import Chroma


# Absolute path so the DB is always found regardless of cwd
_VECTORDB_DIR = str(Path(__file__).parent.parent / "vectordb")
_COLLECTION_NAME = "java_repo"


def _make_doc_id(doc: Document) -> str:
    """
    Deterministic document ID = MD5 of (file_path + chunk_type + chunk_index).
    Guarantees idempotent upserts - re-indexing the same repo
    does not create duplicate vectors.
    """
    meta = doc.metadata
    key = (
        meta.get("file", "")
        + meta.get("chunk_type", "")
        + str(meta.get("chunk_index", 0))
    )
    return hashlib.md5(key.encode()).hexdigest()


def build_vector_store(
    documents: list[Document],
    embeddings,
) -> Chroma:
    """
    Build (or rebuild) the vector store from a list of Documents.
    Uses upsert semantics - safe to call multiple times on the same repo.
    """
    ids = [_make_doc_id(doc) for doc in documents]

    vectordb = Chroma(
        collection_name=_COLLECTION_NAME,
        persist_directory=_VECTORDB_DIR,
        embedding_function=embeddings,
    )

    # Upsert in batches of 500 to stay within Chroma limits
    batch_size = 500
    for i in range(0, len(documents), batch_size):
        batch_docs = documents[i: i + batch_size]
        batch_ids = ids[i: i + batch_size]
        vectordb.add_documents(documents=batch_docs, ids=batch_ids)
        print(f"  Indexed {min(i + batch_size, len(documents))}/{len(documents)} chunks")

    return vectordb


def load_vector_store(embeddings) -> Chroma:
    """Load the existing persisted vector store (read-only)."""
    return Chroma(
        collection_name=_COLLECTION_NAME,
        persist_directory=_VECTORDB_DIR,
        embedding_function=embeddings,
    )
