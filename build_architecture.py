from __future__ import annotations

"""
Phase 5: Architecture Understanding Engine CLI.

Analyses a Java repository and produces:
  data/architecture_report.json       -- structured analysis
  data/architecture_diagrams.md       -- all Mermaid diagrams
  data/architecture_c4.txt            -- C4 model descriptions
  data/onboarding.md                  -- full onboarding document

Prerequisites:
  1. python main.py                   -- ingest the repository
  2. python build_dependency_graph.py -- (optional, enriches layer coupling data)
  3. python build_architecture.py     -- this script

Usage:
  python build_architecture.py
  python build_architecture.py --llm          # use LLM for narrative summaries
  python build_architecture.py --app-name MyApp
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.ingest import load_metadata
from src.architecture import analyze_architecture
from src.architecture.diagram import all_diagrams
from src.architecture.c4 import full_c4_model
from src.architecture.summarizer import summarize_architecture
from src.architecture.onboarding import generate_onboarding


def _section(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def main(use_llm: bool = False, app_name: str = "") -> None:
    _section("Architecture Understanding Engine -- Phase 5")

    print("\nLoading metadata...")
    metadata = load_metadata()
    print(f"  {len(metadata)} files")

    print("\nAnalysing architecture...")
    report = analyze_architecture(metadata)
    print(report.summary())

    # Load dependency graph if available (enriches layer coupling data)
    graph = None
    dep_graph_path = ROOT / "data" / "dependency_graph.json"
    if dep_graph_path.exists():
        try:
            from src.dependency import build_full_graph
            graph = build_full_graph(metadata)
            print(f"\n  Dependency graph loaded: "
                  f"{graph.number_of_nodes()} nodes, "
                  f"{graph.number_of_edges()} edges")
            # Re-run with graph for enriched layer coupling
            from src.architecture.analyzer import analyze
            report = analyze(metadata, graph)
        except Exception as e:
            print(f"  Could not load dependency graph: {e}")

    _section("Generating Diagrams")
    diagrams = all_diagrams(report)
    for name in diagrams:
        print(f"  + {name}")

    _section("Generating C4 Model")
    c4 = full_c4_model(report, app_name)
    print("  System Context, Container, and Component levels generated")

    _section("Generating Summaries")
    llm = None
    if use_llm:
        try:
            from src.llm import load_llm
            llm = load_llm()
            print("  LLM loaded -- generating narrative summaries")
        except Exception as e:
            print(f"  LLM unavailable ({e}) -- using template summaries")
    else:
        print("  Using template summaries (pass --llm for LLM-generated text)")

    summaries = summarize_architecture(report, llm)
    for section in summaries:
        print(f"  + {section}")

    _section("Generating Onboarding Document")
    onboarding = generate_onboarding(report, summaries, app_name)
    print(f"  {len(onboarding.splitlines())} lines generated")

    _section("Writing Output Files")
    out = ROOT / "data"
    out.mkdir(exist_ok=True)

    # Architecture report JSON
    report_path = out / "architecture_report.json"
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  architecture_report.json   ({report_path.stat().st_size // 1024} KB)")

    # Mermaid diagrams
    diag_path = out / "architecture_diagrams.md"
    diag_lines = ["# Architecture Diagrams\n"]
    for name, src in diagrams.items():
        diag_lines.append(f"## {name.replace('_', ' ').title()}\n")
        diag_lines.append(f"```mermaid\n{src}\n```\n")
    diag_path.write_text("\n".join(diag_lines), encoding="utf-8")
    print(f"  architecture_diagrams.md   ({diag_path.stat().st_size // 1024} KB)")

    # C4 model
    c4_path = out / "architecture_c4.txt"
    c4_path.write_text(c4, encoding="utf-8")
    print(f"  architecture_c4.txt        ({c4_path.stat().st_size // 1024} KB)")

    # Onboarding document
    ob_path = out / "onboarding.md"
    ob_path.write_text(onboarding, encoding="utf-8")
    print(f"  onboarding.md              ({ob_path.stat().st_size // 1024} KB)")

    print("\nDone.")
    print(f"\nTo view diagrams: open data/onboarding.md in VS Code "
          f"(install 'Markdown Preview Mermaid Support' extension)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Java Architecture Understanding Engine"
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Use LLM to generate narrative summaries (requires px proxy)"
    )
    parser.add_argument(
        "--app-name",
        default="",
        help="Application name override for diagrams and docs"
    )
    args = parser.parse_args()
    main(use_llm=args.llm, app_name=args.app_name)
