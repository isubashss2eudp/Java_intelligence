"""
Phase 1: Repository ingestion.

Scans a Java repository, extracts AST-based metadata for every .java file,
and writes the result to data/repository_metadata.json.

Usage:
    python main.py
"""

from __future__ import annotations


from pathlib import Path

from src.ingest import ingest_repository, save_metadata


def main():
    print("\n" + "=" * 60)
    print("  Java Repository Intelligence - Ingestion")
    print("=" * 60)

    repo_path = input("\nEnter Java repository path: ").strip()

    if not Path(repo_path).exists():
        print(f"ERROR: Path does not exist: {repo_path}")
        return

    print(f"\nScanning: {repo_path}")
    data = ingest_repository(repo_path)

    if not data:
        print("No Java files found.")
        return

    print(f"\nTotal Java files parsed: {len(data)}")
    save_metadata(data)


if __name__ == "__main__":
    main()
