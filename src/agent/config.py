from __future__ import annotations
"""Agent configuration."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentConfig:
    """Centralised configuration for the RetroDecrypt Agent."""

    # LLM
    model: str = "gemini-2.5-flash"
    temperature: float = 0.1
    max_output_tokens: int = 8192
    max_retries: int = 3

    # Retrieval
    retrieval_k: int = 8
    retrieval_fetch_k: int = 30
    use_hybrid_retrieval: bool = True

    # Agent
    max_iterations: int = 10
    memory_window: int = 6        # turns to keep in context

    # Paths (resolved from project root)
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent)

    @property
    def vectordb_dir(self) -> Path:
        return self.project_root / "vectordb"

    @property
    def metadata_path(self) -> Path:
        return self.project_root / "data" / "repository_metadata.json"

    @property
    def dep_graph_path(self) -> Path:
        return self.project_root / "data" / "dependency_graph.json"

    @property
    def onboarding_path(self) -> Path:
        return self.project_root / "data" / "onboarding.md"
