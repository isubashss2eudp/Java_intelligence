from __future__ import annotations
"""
Multi-Agent RetroDecrypt System -- interactive CLI.

Usage:
    # Ensure px proxy is running first:
    #   python -m px --foreground=1
    #
    python run_multi_agent.py
    python run_multi_agent.py --question "What are the architectural layers?"
    python run_multi_agent.py --verbose   # show agent delegation and tool calls
    python run_multi_agent.py --diagram   # print ASCII graph diagram
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from langchain_core.messages import AIMessage, ToolMessage

from src.agent import create_multi_agent, AgentConfig, initial_state
from src.agent.state import (
    AGENT_SEARCH, AGENT_ARCHITECTURE, AGENT_DEPENDENCY,
    AGENT_DOCS, AGENT_REVIEW,
)


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

_AGENT_LABELS = {
    "search":       "Repository Search Agent",
    "architecture": "Architecture Agent",
    "dependency":   "Dependency Agent",
    "docs":         "Documentation Agent",
    "review":       "Code Review Agent",
    "coordinator":  "Coordinator Agent",
}

_SEP = "-" * 70


def _print_sep(char: str = "-") -> None:
    print(char * 70)


def _print_graph_diagram() -> None:
    print("""
Multi-Agent System Architecture
================================

                      User Query
                          |
                    [COORDINATOR]
                    Gemini 2.5 Flash
                    Structured output
                   /    |    |    \\   \\
             parallel dispatch via Send API
                 /      |    |     \\   \\
          [SEARCH] [ARCH] [DEP] [DOCS] [REVIEW]
          src code  layers  graph  docs  quality
          BM25+vec  modules cycles onboard review
               \\      |    |     /   /
                \\     |    |    /   /
                 [COORDINATOR] <-- results merged
                      |
                 (done? -> FINISH)
                      |
                 [SYNTHESIZER]
                 Integrated answer
                      |
                     END

Legend:
  [COORDINATOR]  -- Routes to specialist agents (sequential or parallel)
  [SEARCH]       -- Uses search_repository tool
  [ARCH]         -- Uses analyze_architecture_tool
  [DEP]          -- Uses analyze_dependencies tool
  [DOCS]         -- Uses get_documentation tool
  [REVIEW]       -- Uses search_repository + explain_code tools
  [SYNTHESIZER]  -- Integrates all results into final answer
""")


def _show_agent_trace(result: dict, verbose: bool = False) -> None:
    """Display which agents were invoked and their results."""
    agent_results = result.get("agent_results", {})
    iterations    = result.get("iterations", 0)
    active        = result.get("active_agents", [])

    if not agent_results:
        return

    print(f"\n  Coordinator cycles: {iterations}")
    print(f"  Agents invoked    : {', '.join(agent_results.keys())}")

    if verbose:
        for agent_name, agent_text in agent_results.items():
            label = _AGENT_LABELS.get(agent_name, agent_name)
            _print_sep(".")
            print(f"  [{label}]")
            preview = agent_text[:400].replace("\n", "\n    ")
            print(f"    {preview}")
            if len(agent_text) > 400:
                print(f"    ... ({len(agent_text)} chars total)")


def _extract_answer(result: dict) -> str:
    final = result.get("final_answer", "")
    if final:
        return final
    # Fallback: last AIMessage
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return "No answer generated."


# ---------------------------------------------------------------------------
# Single question
# ---------------------------------------------------------------------------

def run_question(
    agent,
    query: str,
    history_state: dict | None = None,
    verbose: bool = False,
) -> tuple[str, dict]:
    """
    Run one question through the multi-agent system.

    Args:
        agent:         Compiled multi-agent graph.
        query:         User question string.
        history_state: Previous state for multi-turn conversations (optional).
        verbose:       Show agent delegation details.

    Returns:
        (answer_text, updated_state)
    """
    if history_state:
        # Continuation: append new query, reset routing state
        from langchain_core.messages import HumanMessage
        state = dict(history_state)
        state["messages"]      = list(state.get("messages", [])) + [HumanMessage(content=query)]
        state["query"]         = query
        state["agent_results"] = {}
        state["next_agents"]   = []
        state["active_agents"] = []
        state["iterations"]    = 0
        state["final_answer"]  = ""
        state["task_context"]  = ""
    else:
        state = initial_state(query)

    result = agent.invoke(state)

    if verbose:
        _show_agent_trace(result, verbose=True)

    return _extract_answer(result), result


# ---------------------------------------------------------------------------
# Interactive loop
# ---------------------------------------------------------------------------

def interactive_loop(agent, verbose: bool = False) -> None:
    _print_sep("=")
    print("  RetroDecrypt Multi-Agent System")
    print("  6 Specialised Agents | LangGraph | Gemini 2.5 Flash")
    _print_sep("=")
    print("Commands: exit | clear | agents | diagram | verbose")
    print("Agents: Coordinator, Search, Architecture, Dependency, Docs, Review\n")

    history_state: dict | None = None
    turn = 0

    while True:
        try:
            query = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not query:
            continue
        if query.lower() == "exit":
            print("Goodbye.")
            break
        if query.lower() == "clear":
            history_state = None
            turn = 0
            print("Conversation cleared.")
            continue
        if query.lower() == "agents":
            for key, label in _AGENT_LABELS.items():
                print(f"  {key:<15} {label}")
            continue
        if query.lower() == "diagram":
            _print_graph_diagram()
            continue
        if query.lower() == "verbose":
            verbose = not verbose
            print(f"Verbose mode: {'ON' if verbose else 'OFF'}")
            continue

        turn += 1
        print(f"\n[Turn {turn}] Routing to agents...", end="", flush=True)

        try:
            answer, history_state = run_question(
                agent, query, history_state, verbose
            )
            print("\r" + " " * 40 + "\r", end="")
            _print_sep()
            print(f"Answer:\n{answer}")
            _print_sep()
        except Exception as exc:
            print(f"\n[Error] {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="RetroDecrypt Multi-Agent System")
    parser.add_argument("--question", "-q", default="", help="Single question (non-interactive)")
    parser.add_argument("--verbose",  "-v", action="store_true", help="Show agent delegation")
    parser.add_argument("--diagram",  "-d", action="store_true", help="Print graph diagram and exit")
    args = parser.parse_args()

    if args.diagram:
        _print_graph_diagram()
        return

    print("\nInitialising multi-agent system...")
    config = AgentConfig()
    agent  = create_multi_agent(config)
    print("System ready.\n")

    if args.question:
        answer, result = run_question(agent, args.question, verbose=args.verbose)
        _show_agent_trace(result, verbose=args.verbose)
        _print_sep()
        print(answer)
        _print_sep()
    else:
        interactive_loop(agent, args.verbose)


if __name__ == "__main__":
    main()
