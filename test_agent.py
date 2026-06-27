from __future__ import annotations
"""
Test suite for the LangGraph RetroDecrypt Agent.

Tests are split into:
  Unit tests   -- tool logic, config, memory (no LLM, no network)
  Graph tests  -- graph compilation and routing logic
  Integration  -- end-to-end agent invocation (requires LLM + proxy)

Run offline tests only (no LLM):
    python test_agent.py

Run with LLM (requires px proxy):
    python test_agent.py --with-llm
"""

import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _sep():
    print("-" * 60)


# ---------------------------------------------------------------------------
# 1. Config tests
# ---------------------------------------------------------------------------

def test_config_defaults():
    from src.agent.config import AgentConfig
    cfg = AgentConfig()
    assert cfg.model == "gemini-2.5-flash"
    assert cfg.max_iterations == 10
    assert cfg.memory_window == 6
    assert cfg.vectordb_dir.name == "vectordb"
    assert cfg.metadata_path.name == "repository_metadata.json"
    print("  [OK] AgentConfig defaults")


# ---------------------------------------------------------------------------
# 2. Memory tests
# ---------------------------------------------------------------------------

def test_system_message():
    from src.agent.memory import build_system_message
    from langchain_core.messages import SystemMessage
    msg = build_system_message()
    assert isinstance(msg, SystemMessage)
    assert "RetroDecrypt Agent" in msg.content
    assert len(msg.content) > 100
    print("  [OK] build_system_message")


def test_trim_history_preserves_system():
    from src.agent.config import AgentConfig
    from src.agent.memory import build_system_message, trim_history
    from langchain_core.messages import HumanMessage, AIMessage

    cfg = AgentConfig()
    cfg.memory_window = 2

    messages = [build_system_message()]
    for i in range(10):
        messages.append(HumanMessage(content=f"Q{i}"))
        messages.append(AIMessage(content=f"A{i}"))

    trimmed = trim_history(messages, cfg)

    from langchain_core.messages import SystemMessage
    assert isinstance(trimmed[0], SystemMessage), "System message must be first"
    # Should have system + window*2 messages
    assert len(trimmed) <= 1 + cfg.memory_window * 2 + 4
    print("  [OK] trim_history preserves system message")


def test_format_history():
    from src.agent.memory import format_history_for_display, build_system_message
    from langchain_core.messages import HumanMessage, AIMessage

    msgs = [
        build_system_message(),
        HumanMessage(content="What classes are there?"),
        AIMessage(content="There are 5 classes."),
    ]
    output = format_history_for_display(msgs)
    assert "[System]" in output
    assert "[Human]" in output
    assert "[Agent]" in output
    print("  [OK] format_history_for_display")


# ---------------------------------------------------------------------------
# 3. Tool tests (offline -- no LLM, uses local files)
# ---------------------------------------------------------------------------

def test_tools_are_callable():
    from src.agent.tools import ALL_TOOLS
    assert len(ALL_TOOLS) == 5
    names = {t.name for t in ALL_TOOLS}
    assert "search_repository" in names
    assert "analyze_dependencies" in names
    assert "analyze_architecture_tool" in names
    assert "explain_code" in names
    assert "get_documentation" in names
    print("  [OK] ALL_TOOLS has 5 tools")


def test_tools_have_descriptions():
    from src.agent.tools import ALL_TOOLS
    for tool in ALL_TOOLS:
        assert tool.description, f"Tool {tool.name} has no description"
        assert len(tool.description) > 50, f"Tool {tool.name} description too short"
    print("  [OK] all tools have descriptions")


def test_analyze_architecture_tool_summary():
    """Test architecture tool without LLM (uses local analysis)."""
    from src.ingest import load_metadata
    from src.architecture import analyze_architecture
    from src.agent.tools import _ARCH_REPORT
    import src.agent.tools as tool_module

    # Pre-load the report into the singleton
    if Path("data/repository_metadata.json").exists():
        meta = load_metadata()
        tool_module._ARCH_REPORT = analyze_architecture(meta)
        result = tool_module.analyze_architecture_tool.invoke(
            {"aspect": "summary"}
        )
        assert "Layer Breakdown" in result or "Architecture" in result
        print("  [OK] analyze_architecture_tool (summary)")
    else:
        print("  [SKIP] analyze_architecture_tool -- no metadata.json")


def test_analyze_dependencies_stats():
    """Test dependency tool stats query (uses local graph)."""
    from src.ingest import load_metadata
    from src.dependency import build_full_graph
    import src.agent.tools as tool_module

    if Path("data/repository_metadata.json").exists():
        meta = load_metadata()
        tool_module._GRAPH = build_full_graph(meta)
        result = tool_module.analyze_dependencies.invoke(
            {"query_type": "stats", "class_name": "", "source_class": "", "target_class": ""}
        )
        assert "total_classes" in result
        print("  [OK] analyze_dependencies (stats)")
    else:
        print("  [SKIP] analyze_dependencies -- no metadata.json")


def test_get_documentation_overview():
    """Test doc tool with local onboarding.md."""
    if Path("data/onboarding.md").exists():
        from src.agent.tools import get_documentation
        result = get_documentation.invoke({"section": "overview"})
        assert len(result) > 50
        assert "Project Overview" in result or "Base Package" in result or "Spring Boot" in result
        print("  [OK] get_documentation (overview)")
    else:
        print("  [SKIP] get_documentation -- no onboarding.md")


def test_get_documentation_invalid_section():
    """Test graceful handling of bad section name."""
    if Path("data/onboarding.md").exists():
        from src.agent.tools import get_documentation
        result = get_documentation.invoke({"section": "nonexistent_xyz"})
        assert "Unknown section" in result or "not found" in result
        print("  [OK] get_documentation (invalid section handled)")
    else:
        print("  [SKIP] get_documentation -- no onboarding.md")


def test_analyze_dependencies_cycles():
    """Test cycle detection -- sample_spring_repo has NotificationService<->AlertService."""
    from src.ingest import ingest_repository
    from src.dependency import build_full_graph
    import src.agent.tools as tool_module

    sample = ROOT / "sample_spring_repo"
    if sample.exists():
        from src.ingest import ingest_repository, save_metadata
        meta = ingest_repository(str(sample))
        tool_module._GRAPH = build_full_graph(meta)

        result = tool_module.analyze_dependencies.invoke(
            {"query_type": "cycles", "class_name": "", "source_class": "", "target_class": ""}
        )
        assert "NotificationService" in result or "AlertService" in result or "Circular" in result
        print("  [OK] analyze_dependencies (cycles)")
    else:
        print("  [SKIP] cycle test -- no sample_spring_repo")


def test_analyze_dependencies_who_depends_on():
    """Test who_depends_on query."""
    from src.ingest import ingest_repository
    from src.dependency import build_full_graph
    import src.agent.tools as tool_module

    sample = ROOT / "sample_spring_repo"
    if sample.exists():
        meta = ingest_repository(str(sample))
        tool_module._GRAPH = build_full_graph(meta)

        result = tool_module.analyze_dependencies.invoke({
            "query_type": "who_depends_on",
            "class_name": "CustomerRepository",
            "source_class": "",
            "target_class": "",
        })
        assert "CustomerService" in result or "OrderService" in result
        print("  [OK] analyze_dependencies (who_depends_on)")
    else:
        print("  [SKIP] who_depends_on -- no sample_spring_repo")


# ---------------------------------------------------------------------------
# 4. Graph compilation test (no LLM call)
# ---------------------------------------------------------------------------

def test_graph_compiles():
    """Verify the graph compiles without errors."""
    from src.agent.graph import create_agent, AgentConfig
    config = AgentConfig()
    agent = create_agent(config)
    assert agent is not None
    # Check the graph has agent and tools nodes
    assert "agent" in agent.get_graph().nodes
    assert "tools" in agent.get_graph().nodes
    print("  [OK] graph compiles (agent + tools nodes)")


def test_graph_structure():
    """Verify edge structure: agent->tools->agent and agent->END."""
    from src.agent.graph import create_agent, AgentConfig
    agent = create_agent(AgentConfig())
    graph = agent.get_graph()

    node_names = set(graph.nodes.keys())
    assert "__start__" in node_names
    assert "agent" in node_names
    assert "tools" in node_names
    print("  [OK] graph structure (__start__, agent, tools)")


# ---------------------------------------------------------------------------
# 5. Integration test (requires LLM)
# ---------------------------------------------------------------------------

def test_agent_single_question(verbose: bool = False):
    """
    Full end-to-end: ask the agent a question and verify it uses a tool.
    Requires px proxy to be running.
    """
    from src.agent import create_agent, AgentConfig
    from src.agent.memory import build_system_message
    from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

    config = AgentConfig()
    agent = create_agent(config)

    messages = [
        build_system_message(),
        HumanMessage(content="What architectural layers does this repository have? Use the architecture tool."),
    ]

    print("  Invoking agent (may take 10-20s)...")
    result = agent.invoke({"messages": messages})
    out_msgs = list(result["messages"])

    # Check that at least one tool was called
    tool_calls = [
        m for m in out_msgs
        if isinstance(m, AIMessage) and m.tool_calls
    ]
    tool_results = [m for m in out_msgs if isinstance(m, ToolMessage)]

    if verbose:
        for msg in out_msgs:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                for call in msg.tool_calls:
                    print(f"    Tool called: {call['name']}")
            elif isinstance(msg, ToolMessage):
                print(f"    Tool result [{msg.name}]: {str(msg.content)[:100]}...")

    assert len(tool_calls) >= 1, "Agent should have called at least one tool"
    assert len(tool_results) >= 1, "Agent should have received at least one tool result"

    final = next(
        (m.content for m in reversed(out_msgs)
         if isinstance(m, AIMessage) and m.content), ""
    )
    assert len(final) > 50, f"Final answer too short: {final}"
    print(f"  [OK] single question: tool calls={len(tool_calls)}, "
          f"answer length={len(final)} chars")


def test_agent_multi_turn(verbose: bool = False):
    """
    Multi-turn conversation test: asks two follow-up questions.
    """
    from src.agent import create_agent, AgentConfig
    from src.agent.memory import build_system_message
    from langchain_core.messages import HumanMessage, AIMessage

    config = AgentConfig()
    agent = create_agent(config)

    history = [build_system_message()]

    questions = [
        "List the services in this repository.",
        "Which of those services has the most dependencies?",
    ]

    for i, q in enumerate(questions, 1):
        print(f"  Turn {i}: {q[:50]}...")
        history.append(HumanMessage(content=q))
        result = agent.invoke({"messages": history})
        history = list(result["messages"])

        final = next(
            (m.content for m in reversed(history)
             if isinstance(m, AIMessage) and m.content), ""
        )
        assert len(final) > 20, f"Turn {i} answer too short"
        print(f"    Answer preview: {final[:80]}...")

    print(f"  [OK] multi-turn: {len(questions)} turns, "
          f"history={len(history)} messages")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent test suite")
    parser.add_argument("--with-llm", action="store_true",
                        help="Run integration tests (requires px proxy + LLM)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    _sep()
    print("  RetroDecrypt Agent -- Test Suite")
    _sep()

    offline_tests = [
        test_config_defaults,
        test_system_message,
        test_trim_history_preserves_system,
        test_format_history,
        test_tools_are_callable,
        test_tools_have_descriptions,
        test_analyze_architecture_tool_summary,
        test_analyze_dependencies_stats,
        test_get_documentation_overview,
        test_get_documentation_invalid_section,
        test_analyze_dependencies_cycles,
        test_analyze_dependencies_who_depends_on,
        test_graph_compiles,
        test_graph_structure,
    ]

    llm_tests = [
        lambda: test_agent_single_question(args.verbose),
        lambda: test_agent_multi_turn(args.verbose),
    ]

    passed = failed = 0
    for test in offline_tests:
        try:
            test()
            passed += 1
        except Exception as exc:
            import traceback
            print(f"  [FAIL] {test.__name__}: {exc}")
            if args.verbose:
                traceback.print_exc()
            failed += 1

    if args.with_llm:
        print("\n  [LLM Integration Tests]")
        for test in llm_tests:
            try:
                test()
                passed += 1
            except Exception as exc:
                import traceback
                print(f"  [FAIL] {test.__name__ if hasattr(test, '__name__') else 'llm_test'}: {exc}")
                if args.verbose:
                    traceback.print_exc()
                failed += 1
    else:
        print("\n  (Skipping LLM tests -- pass --with-llm to run them)")

    _sep()
    print(f"  Results: {passed} passed, {failed} failed")
    _sep()

    if failed:
        raise SystemExit(1)
