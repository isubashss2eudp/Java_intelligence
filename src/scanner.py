from __future__ import annotations

from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".java",
    ".xml",
    ".properties",
    ".yaml",
    ".yml",
    ".md",
}

# Directories that should never be scanned
EXCLUDED_DIRS = {
    "target",
    "build",
    ".git",
    ".gradle",
    ".mvn",
    "node_modules",
    ".idea",
    ".vscode",
    "__pycache__",
    "generated-sources",
    "generated-test-sources",
    "test-classes",
    "classes",
}


def _is_excluded(path: Path) -> bool:
    """Return True if any component of the path is an excluded directory."""
    return any(part in EXCLUDED_DIRS for part in path.parts)


def scan_repository(repo_path: str):
    """
    Recursively scan repo_path and return all supported source files,
    excluding build artefacts and IDE/VCS directories.
    """
    files = []
    root = Path(repo_path)

    for file in root.rglob("*"):
        if not file.is_file():
            continue
        if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if _is_excluded(file.relative_to(root)):
            continue
        files.append(file)

    return files
