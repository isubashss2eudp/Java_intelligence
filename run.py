"""
RetroDecrypt Platform — Unified Entry Point.

Usage:
    python run.py

Flow:
  1. Asks which Java repository to analyse (always prompted).
     If analysis data already exists you can reuse it or pick a new repo.
  2. Runs the analysis pipeline (Phases 1-5) if needed.
  3. Collects your user profile (name, role, Java experience, purpose, depth).
  4. Loads the configured LLM.
  5. Generates a tailored .docx report in C:/temp with LLM-written analysis.
  6. Launches the interactive Q&A chat.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path regardless of how this script is run
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sep(char: str = "=", width: int = 62) -> None:
    print(char * width)


def _check_existing_data() -> tuple:
    """
    Return (exists: bool, file_count: int) for previously ingested data.
    """
    path = ROOT / "data" / "repository_metadata.json"
    if path.exists():
        try:
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
            return True, len(data)
        except Exception:
            pass
    return False, 0


def _ask_repo_choice() -> str | None:
    """
    Always ask the user what codebase to work with.

    Returns
    -------
    str or None
        Path string if a new repository should be ingested.
        None if the user chooses to reuse existing data.
    """
    exists, count = _check_existing_data()

    if exists:
        print(f"\n  Found existing analysis data: {count} source file(s) in data/")
        print("\n  What would you like to do?")
        print("   1. Use the existing analysis data")
        print("   2. Analyse a different / new Java repository")
        while True:
            choice = input("\n  Enter choice (1 or 2): ").strip()
            if choice == "1":
                return None          # reuse existing
            if choice == "2":
                break
            print("  Please enter 1 or 2.")

    # Prompt for the repository path
    print()
    while True:
        path = input("  Java repository path: ").strip()
        if not path:
            print("  Path cannot be empty.")
            continue
        if not Path(path).exists():
            print(f"  Path does not exist: {path}  — please try again.")
            continue
        return path


def _run_ingestion_pipeline(repo_path: str) -> None:
    """
    Run Phase 1 (ingest) + Phase 2 (vector DB) + Phase 4 (dependencies)
    + Phase 5 (architecture) sequentially so all downstream features work.
    """
    from src.ingest import ingest_repository, save_metadata
    from src.chunker import build_documents
    from src.embeddings import load_embeddings
    from src.vector_store import build_vector_store

    print("\n" + "─" * 62)
    print("  Phase 1 — Repository Ingestion")
    print("─" * 62)
    data = ingest_repository(repo_path)
    if not data:
        print("ERROR: No Java files found at that path. Check the path and try again.")
        sys.exit(1)
    save_metadata(data)

    print("\n" + "─" * 62)
    print("  Phase 2 — Building Vector Index")
    print("─" * 62)
    print("  Loading embedding model (first run may take ~30 s)...")
    embeddings = load_embeddings()
    documents  = build_documents(data)
    print(f"  {len(documents)} chunks created")
    build_vector_store(documents, embeddings)
    print("  Vector index ready.")

    print("\n" + "─" * 62)
    print("  Phase 4 — Dependency Analysis")
    print("─" * 62)
    try:
        from src.dependency import build_full_graph
        from src.dependency.analyzer import analyze
        from src.dependency.exporter import save_json, save_adjacency_json, save_dot
        import json

        G = build_full_graph(data)
        out = ROOT / "data"
        save_json(G, out / "dependency_graph.json")
        save_adjacency_json(G, out / "dependency_adjacency.json")
        save_dot(G, out / "dependency_graph.dot")
        report = analyze(G)
        (out / "dependency_analysis.json").write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )
        print(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    except Exception as exc:
        print(f"  Dependency analysis failed (non-fatal): {exc}")

    print("\n" + "─" * 62)
    print("  Phase 5 — Architecture Analysis")
    print("─" * 62)
    try:
        import json
        from src.architecture import analyze_architecture
        from src.architecture.diagram import all_diagrams
        from src.architecture.c4 import full_c4_model
        from src.architecture.onboarding import generate_onboarding
        from src.architecture.summarizer import summarize_architecture

        arch_report = analyze_architecture(data)
        out = ROOT / "data"
        (out / "architecture_report.json").write_text(
            json.dumps(arch_report.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        diagrams = all_diagrams(arch_report)
        diag_lines = ["# Architecture Diagrams\n"]
        for name, src in diagrams.items():
            diag_lines.append(f"## {name.replace('_', ' ').title()}\n")
            diag_lines.append(f"```mermaid\n{src}\n```\n")
        (out / "architecture_diagrams.md").write_text(
            "\n".join(diag_lines), encoding="utf-8"
        )
        c4 = full_c4_model(arch_report, "")
        (out / "architecture_c4.txt").write_text(c4, encoding="utf-8")
        summaries = summarize_architecture(arch_report)
        onboarding = generate_onboarding(arch_report, summaries, "")
        (out / "onboarding.md").write_text(onboarding, encoding="utf-8")
        print(f"  Architecture report ready: {arch_report.stats.get('layer_count', 0)} layers")
    except Exception as exc:
        print(f"  Architecture analysis failed (non-fatal): {exc}")

    print("\n  ✓ Analysis pipeline complete.\n")


def _load_llm():
    """Load the configured LLM.  Returns None on failure (graceful degradation)."""
    try:
        from src.llm import load_llm
        llm = load_llm()
        from src.llm import get_active_provider
        print(f"  LLM ready: {get_active_provider()}")
        return llm
    except Exception as exc:
        print(f"  ⚠  LLM unavailable ({exc}).")
        print("     Check your .env API key. Documentation will use template content.")
        return None


def _generate_doc(profile, llm=None) -> None:
    """Generate the .docx report and print its path."""
    from src.doc_generator import generate_documentation

    print("\n" + "─" * 62)
    print("  Generating personalised documentation…")
    print("─" * 62)
    try:
        doc_path = generate_documentation(profile, llm=llm)
        print(f"\n  ✓  Documentation saved to:")
        print(f"     {doc_path}")
        print(f"\n  Level : {profile.knowledge_level.title()}")
        print(f"  Purpose: {profile.purpose}")
    except ImportError as exc:
        print(f"\n  ⚠  Could not generate .docx: {exc}")
    except Exception as exc:
        print(f"\n  ⚠  Documentation generation failed: {exc}")


def _run_chat() -> None:
    """Start the interactive Q&A chat (Phase 3 / 7 hybrid retrieval)."""
    from src.chat import main as chat_main
    chat_main()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    _sep()
    print("  RetroDecrypt Platform")
    print("  AI-powered Java repository analysis")
    _sep()

    # ---- Step 1: Always ask which codebase to work with ----------------
    repo_path = _ask_repo_choice()

    if repo_path is not None:
        _run_ingestion_pipeline(repo_path)
    else:
        _, count = _check_existing_data()
        print(f"\n  Reusing existing analysis data ({count} files).")

    # ---- Step 2: Collect user profile ----------------------------------
    from src.user_profile import collect_user_profile
    profile = collect_user_profile()

    # ---- Step 3: Load LLM for documentation ----------------------------
    print("\n" + "─" * 62)
    print("  Loading LLM for documentation generation…")
    print("─" * 62)
    llm = _load_llm()

    # ---- Step 4: Generate .docx ----------------------------------------
    _generate_doc(profile, llm=llm)

    # ---- Step 5: Chat mode ---------------------------------------------
    print("\n" + "─" * 62)
    print("  Starting interactive Q&A chat mode…")
    print("  (Type 'exit' to quit, 'clear' to reset conversation history)")
    print("─" * 62)

    _run_chat()


if __name__ == "__main__":
    main()
