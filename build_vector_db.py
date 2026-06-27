"""
Build (or rebuild) the ChromaDB vector store from repository metadata.

Usage:
    python build_vector_db.py

Prerequisites:
    Run main.py first to generate data/repository_metadata.json.
"""

from __future__ import annotations


from src.ingest import load_metadata
from src.chunker import build_documents
from src.embeddings import load_embeddings
from src.vector_store import build_vector_store


def main():
    print("\nLoading metadata...")
    repository_data = load_metadata()
    print(f"  {len(repository_data)} files loaded")

    print("\nBuilding document chunks...")
    documents = build_documents(repository_data)
    print(f"  {len(documents)} chunks created")

    print("\nLoading embedding model...")
    embeddings = load_embeddings()

    print("\nIndexing chunks into ChromaDB...")
    build_vector_store(documents, embeddings)

    print("\nVector database ready.")


if __name__ == "__main__":
    main()
