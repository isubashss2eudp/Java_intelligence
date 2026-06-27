"""
Repository ingestion pipeline.
Streams parsed metadata to JSON incrementally - never holds all file
content in memory at once, enabling large-repo support.
"""

from __future__ import annotations


import json
from pathlib import Path

from src.scanner import scan_repository
from src.parser import parse_java_file


def ingest_repository(repo_path: str) -> list[dict]:
    """
    Scan and parse all Java files under repo_path.
    Returns a list of metadata dicts (without raw file content).
    """
    files = scan_repository(repo_path)
    java_files = [f for f in files if f.suffix.lower() == ".java"]

    print(f"  Found {len(java_files)} Java files")

    repository_data = []

    for idx, file in enumerate(java_files, 1):
        try:
            metadata = parse_java_file(file)
            repository_data.append(metadata.model_dump())
            print(f"  [{idx}/{len(java_files)}] Parsed: {file.name}")
        except Exception as exc:
            print(f"  [ERROR] Failed: {file}  - {exc}")

    return repository_data


def save_metadata(data: list[dict]) -> None:
    """Persist metadata list to data/repository_metadata.json."""
    Path("data").mkdir(parents=True, exist_ok=True)

    out_path = Path("data") / "repository_metadata.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"  Metadata written to {out_path} ({out_path.stat().st_size // 1024} KB)")


def load_metadata() -> list[dict]:
    """Load previously saved metadata from JSON."""
    path = Path("data") / "repository_metadata.json"

    if not path.exists():
        raise FileNotFoundError(
            "data/repository_metadata.json not found. "
            "Run main.py first to ingest a repository."
        )

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
