from __future__ import annotations
"""
RetroDecrypt Agent -- interactive CLI runner.

Usage:
    # Make sure px proxy is running first:
    #   python -m px --foreground=1
    #
    python run_agent.py
    python run_agent.py --question "Which services depend on CustomerRepository?"
    python run_agent.py --verbose   # show tool calls and reasoning steps
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from src.agent import create_agent, AgentConfig
from src.agent.memory import build_system_message, format_history_for_display


def _print_separator(char: str = "-", width: int = 60) -> None:
    print(char * width)


def _extract_final_answer(messages: list) -> str:
    """Get the last AI text response (not tool calls)."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    return "No answer generated."


def _show_trace(messages: list) -> None:
    """Print the reasoning trace (tool calls and results)."""
    print("\n[Reasoning Trace]")
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for call in msg.tool_calls:
                print(f"  -> Tool: {call['name']}")
                args = {k: str(v)[:60] for k, v in call.get("args", {}).items()}
                for k, v in args.items():
                    print(f"       {k}: {v}")
        elif isinstance(msg, ToolMessage):
            preview = str(msg.content)[:120].replace("\n", " ")
            print(f"  <- Result [{msg.name}]: {preview}...")
    print()


def run_question(
    agent,
    question: str,
    history: list,
    verbose: bool = False,
) -> tuple[str, list]:
    """
    Run a single question through the agent.

    Returns:
        (answer_text, updated_history)
    """
    # Prepend system message if history is empty
    if not history:
        history = [build_system_message()]

    history.append(HumanMessage(content=question))

    result = agent.invoke({"messages": history})
    new_messages = list(result["messages"])

    if verbose:
        _show_trace(new_messages)

    answer = _extract_final_answer(new_messages)
    return answer, new_messages


def interactive_loop(agent, verbose: bool = False) -> None:
    """Run an interactive multi-turn conversation."""
    _print_separator("=")
    print("  RetroDecrypt Agent  (LangGraph + Gemini 2.5 Flash)")
    _print_separator("=")
    print("Commands: exit | clear | history | verbose")
    print("Ask anything about the Java repository.\n")

    history: list = []
    turn = 0

    while True:
        try:
            question = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not question:
            continue

        if question.lower() == "exit":
            print("Goodbye.")
            break

        if question.lower() == "clear":
            history = []
            turn = 0
            print("Conversation history cleared.")
            continue

        if question.lower() == "history":
            print(format_history_for_display(history))
            continue

        if question.lower() == "verbose":
            verbose = not verbose
            print(f"Verbose mode: {'ON' if verbose else 'OFF'}")
            continue

        turn += 1
        print(f"\n[Turn {turn}] Thinking", end="", flush=True)

        try:
            answer, history = run_question(agent, question, history, verbose)
            print("\r" + " " * 30 + "\r", end="")  # clear "Thinking..."
            _print_separator()
            print(f"Agent: {answer}")
            _print_separator()
        except Exception as exc:
            print(f"\n[Error] {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RetroDecrypt LangGraph Agent"
    )
    parser.add_argument(
        "--question", "-q",
        default="",
        help="Single question mode (non-interactive)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show tool calls and reasoning steps"
    )
    args = parser.parse_args()

    print("\nInitialising agent (loading models)...")
    config = AgentConfig()
    agent = create_agent(config)
    print("Agent ready.\n")

    if args.question:
        answer, _ = run_question(agent, args.question, [], args.verbose)
        _print_separator()
        print(answer)
        _print_separator()
    else:
        interactive_loop(agent, args.verbose)


if __name__ == "__main__":
    main()
