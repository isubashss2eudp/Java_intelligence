from __future__ import annotations
"""
Test suite for the Multi-Agent RetroDecrypt System.

Tests:
  Unit  -- state definition, routing logic, agent construction (no LLM)
  Graph -- graph compilation and edge structure
  LLM   -- full agent invocation (requires px proxy)

Run offline tests:
    python test_multi_agent.py

Run with LLM:
    python test_multi_agent.py --with-llm --verbose
"""
import sys
import argparse
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def _sep():
    print("-" * 60)


# ---------------------------------------------------------------------------
# 1. State tests
# ---------------------------------------------------------------------------

def test_state_merge_reducer():
    """Parallel writes to agent_results are merged correctly."""
    from src.agent.state import _merge_dicts
    a = {"search": "code result"}
    b = {"dependency": "graph result"}
    merged = _merge_dicts(a, b)
    assert merged == {"search": "code result", "dependency": "graph result"}
    print("  [OK] _merge_dicts reducer")


def test_state_merge_overwrite():
    """Later write wins on key collision."""
    from src.agent.state import _merge_dicts
    a = {"search": "old result"}
    b = {"search": "new result"}
    merged = _merge_dicts(a, b)
    assert merged["search"] == "new result"
    print("  [OK] _merge_dicts overwrites on collision")


def test_initial_state():
    from src.agent import initial_state
    state = initial_state("What layers exist?")
    assert state["query"]        == "What layers exist?"
    assert state["iterations"]   == 0
    assert state["agent_results"] == {}
    assert state["final_answer"] == ""
    assert len(state["messages"]) == 1
    print("  [OK] initial_state factory")


def test_agent_name_constants():
    from src.agent.state import (
        AGENT_SEARCH, AGENT_ARCHITECTURE, AGENT_DEPENDENCY,
        AGENT_DOCS, AGENT_REVIEW, AGENT_FINISH, ALL_AGENT_NAMES,
    )
    assert AGENT_SEARCH        == "search"
    assert AGENT_ARCHITECTURE  == "architecture"
    assert AGENT_DEPENDENCY    == "dependency"
    assert AGENT_DOCS          == "docs"
    assert AGENT_REVIEW        == "review"
    assert AGENT_FINISH        == "FINISH"
    assert len(ALL_AGENT_NAMES) == 5
    print("  [OK] agent name constants")


# ---------------------------------------------------------------------------
# 2. Coordinator tests
# ---------------------------------------------------------------------------

def test_coordinator_system_prompt():
    from src.agent.agents.coordinator import COORDINATOR_SYSTEM
    assert "Coordinator" in COORDINATOR_SYSTEM
    assert "search" in COORDINATOR_SYSTEM
    assert "architecture" in COORDINATOR_SYSTEM
    assert "dependency" in COORDINATOR_SYSTEM
    assert len(COORDINATOR_SYSTEM) > 200
    print("  [OK] coordinator system prompt")


def test_synthesizer_system_prompt():
    from src.agent.agents.coordinator import SYNTHESIZER_SYSTEM
    assert "synthesiz" in SYNTHESIZER_SYSTEM.lower()
    assert len(SYNTHESIZER_SYSTEM) > 100
    print("  [OK] synthesizer system prompt")


def test_routing_decision_model():
    from src.agent.agents.coordinator import RoutingDecision
    decision = RoutingDecision(
        next_agents=["search", "dependency"],
        reasoning="Query spans code and graph",
        task_context="focus on CustomerRepository",
    )
    assert "search" in decision.next_agents
    assert "dependency" in decision.next_agents
    assert decision.reasoning != ""
    print("  [OK] RoutingDecision Pydantic model")


# ---------------------------------------------------------------------------
# 3. Specialist agent tests
# ---------------------------------------------------------------------------

def test_specialist_system_prompts():
    from src.agent.agents.specialists import (
        _SEARCH_SYSTEM, _ARCHITECTURE_SYSTEM, _DEPENDENCY_SYSTEM,
        _DOCS_SYSTEM, _REVIEW_SYSTEM,
    )
    for name, prompt in [
        ("search", _SEARCH_SYSTEM),
        ("architecture", _ARCHITECTURE_SYSTEM),
        ("dependency", _DEPENDENCY_SYSTEM),
        ("docs", _DOCS_SYSTEM),
        ("review", _REVIEW_SYSTEM),
    ]:
        assert len(prompt) > 100, f"{name} prompt too short"
        assert "Your role" in prompt or "role" in prompt.lower(), f"{name} missing role"
    print("  [OK] all specialist system prompts")


def test_specialists_write_correct_keys():
    """
    Verify each specialist writes to the correct key in agent_results.
    We mock the _run_specialist function to avoid LLM calls.
    """
    import src.agent.agents.specialists as spec_module

    # Patch _run_specialist to return a deterministic string
    original = spec_module._run_specialist
    spec_module._run_specialist = lambda **kw: f"result from {kw['agent_name']}"

    from src.agent.config import AgentConfig

    # Create a fake LLM that won't be called
    class FakeLLM:
        def bind_tools(self, tools):
            return self
        def with_structured_output(self, schema):
            return self
        def invoke(self, msgs):
            from langchain_core.messages import AIMessage
            return AIMessage(content="done")

    fake_llm = FakeLLM()
    state = {
        "query": "test",
        "task_context": "",
        "agent_results": {},
    }

    expected_keys = {
        "search":       spec_module.make_search_node(fake_llm),
        "architecture": spec_module.make_architecture_node(fake_llm),
        "dependency":   spec_module.make_dependency_node(fake_llm),
        "docs":         spec_module.make_docs_node(fake_llm),
        "review":       spec_module.make_review_node(fake_llm),
    }

    for key, node_fn in expected_keys.items():
        result = node_fn(state)
        assert key in result["agent_results"], f"{key} agent wrote wrong key"
        assert result["agent_results"][key] == f"result from {key}"

    spec_module._run_specialist = original
    print("  [OK] specialists write correct agent_results keys")


# ---------------------------------------------------------------------------
# 4. Routing function tests
# ---------------------------------------------------------------------------

def test_route_single_agent():
    from src.agent.multi_graph import _route_from_coordinator, NODE_SEARCH
    state = {
        "next_agents": ["search"],
        "iterations":  1,
    }
    result = _route_from_coordinator(state)
    assert result == NODE_SEARCH, f"Expected {NODE_SEARCH}, got {result}"
    print("  [OK] route_from_coordinator: single agent")


def test_route_finish():
    from src.agent.multi_graph import _route_from_coordinator, NODE_SYNTHESIZER
    state = {
        "next_agents": ["FINISH"],
        "iterations":  1,
    }
    result = _route_from_coordinator(state)
    assert result == NODE_SYNTHESIZER
    print("  [OK] route_from_coordinator: FINISH -> synthesizer")


def test_route_parallel():
    from src.agent.multi_graph import _route_from_coordinator
    from langgraph.types import Send
    state = {
        "next_agents": ["search", "dependency"],
        "iterations":  1,
        "query": "test",
        "task_context": "",
        "agent_results": {},
        "active_agents": [],
        "messages": [],
        "final_answer": "",
    }
    result = _route_from_coordinator(state)
    assert isinstance(result, list), "Parallel routing should return a list"
    assert all(isinstance(r, Send) for r in result), "Each item should be a Send"
    assert len(result) == 2
    print("  [OK] route_from_coordinator: parallel -> Send list")


def test_route_iteration_cap():
    from src.agent.multi_graph import _route_from_coordinator, NODE_SYNTHESIZER
    from src.agent.state import MAX_ITERATIONS
    state = {
        "next_agents": ["search"],
        "iterations":  MAX_ITERATIONS,  # at cap
    }
    result = _route_from_coordinator(state)
    assert result == NODE_SYNTHESIZER, "Should force synthesizer at iteration cap"
    print("  [OK] route_from_coordinator: iteration cap -> synthesizer")


def test_route_unknown_agents_filtered():
    from src.agent.multi_graph import _route_from_coordinator, NODE_SYNTHESIZER
    state = {
        "next_agents": ["unknown_agent_xyz"],
        "iterations":  1,
    }
    result = _route_from_coordinator(state)
    assert result == NODE_SYNTHESIZER, "Unknown agents should fall through to synthesizer"
    print("  [OK] route_from_coordinator: unknown agents filtered")


# ---------------------------------------------------------------------------
# 5. Graph compilation tests
# ---------------------------------------------------------------------------

def test_multi_agent_graph_compiles():
    from src.agent import create_multi_agent, AgentConfig
    agent = create_multi_agent(AgentConfig())
    assert agent is not None
    graph = agent.get_graph()
    node_names = set(graph.nodes.keys())
    assert "coordinator" in node_names
    assert "synthesizer" in node_names
    assert "search_agent" in node_names
    assert "architecture_agent" in node_names
    assert "dependency_agent" in node_names
    assert "docs_agent" in node_names
    assert "review_agent" in node_names
    print(f"  [OK] multi-agent graph compiles ({len(node_names)} nodes)")


def test_graph_node_count():
    from src.agent import create_multi_agent, AgentConfig
    agent  = create_multi_agent(AgentConfig())
    graph  = agent.get_graph()
    # __start__, coordinator, synthesizer, 5 specialists = 8 nodes min
    assert len(graph.nodes) >= 8, f"Expected >= 8 nodes, got {len(graph.nodes)}"
    print(f"  [OK] graph has {len(graph.nodes)} nodes")


# ---------------------------------------------------------------------------
# 6. LLM integration tests
# ---------------------------------------------------------------------------

def test_single_agent_dispatch(verbose: bool = False):
    """Single-domain question -> coordinator routes to one agent."""
    from src.agent import create_multi_agent, AgentConfig, initial_state
    agent  = create_multi_agent(AgentConfig())
    state  = initial_state("What architectural layers does the repository have?")

    print("  Invoking (may take 20-40s for multi-agent)...")
    result = agent.invoke(state)

    answer   = result.get("final_answer", "")
    results  = result.get("agent_results", {})
    iters    = result.get("iterations", 0)

    assert len(answer) > 50, f"Answer too short: {answer}"
    assert len(results) >= 1, "At least one agent should have been invoked"

    if verbose:
        print(f"    Agents invoked: {list(results.keys())}")
        print(f"    Coordinator cycles: {iters}")
        print(f"    Answer preview: {answer[:150]}...")

    print(f"  [OK] single-domain: {list(results.keys())}, {iters} cycles")


def test_multi_agent_parallel_dispatch(verbose: bool = False):
    """
    Multi-domain question -> coordinator dispatches to multiple agents,
    possibly in parallel.
    """
    from src.agent import create_multi_agent, AgentConfig, initial_state
    agent = create_multi_agent(AgentConfig())
    state = initial_state(
        "What services exist in this codebase and what are the circular dependencies?"
    )

    print("  Invoking (may take 30-60s for multi-agent parallel)...")
    result = agent.invoke(state)

    answer  = result.get("final_answer", "")
    results = result.get("agent_results", {})
    iters   = result.get("iterations", 0)

    assert len(answer) > 50
    assert len(results) >= 1

    if verbose:
        print(f"    Agents invoked: {list(results.keys())}")
        print(f"    Coordinator cycles: {iters}")
        print(f"    Answer preview: {answer[:200]}...")

    print(f"  [OK] multi-domain: {list(results.keys())}, {iters} cycles")


def test_multi_turn_conversation(verbose: bool = False):
    """Two-turn conversation maintains context."""
    from src.agent import create_multi_agent, AgentConfig, initial_state
    from run_multi_agent import run_question

    agent = create_multi_agent(AgentConfig())
    state = None

    turns = [
        "What services exist in this repository?",
        "Which of those services has the most dependencies?",
    ]

    for i, query in enumerate(turns, 1):
        print(f"  Turn {i}: {query[:50]}...")
        answer, state = run_question(agent, query, state, verbose)
        assert len(answer) > 20, f"Turn {i} answer too short"
        if verbose:
            print(f"    Answer: {answer[:100]}...")

    print(f"  [OK] multi-turn: {len(turns)} turns completed")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-agent test suite")
    parser.add_argument("--with-llm", action="store_true",
                        help="Run LLM integration tests (requires px + network)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    _sep()
    print("  Multi-Agent System -- Test Suite")
    _sep()

    offline_tests = [
        # State
        test_state_merge_reducer,
        test_state_merge_overwrite,
        test_initial_state,
        test_agent_name_constants,
        # Coordinator
        test_coordinator_system_prompt,
        test_synthesizer_system_prompt,
        test_routing_decision_model,
        # Specialists
        test_specialist_system_prompts,
        test_specialists_write_correct_keys,
        # Routing
        test_route_single_agent,
        test_route_finish,
        test_route_parallel,
        test_route_iteration_cap,
        test_route_unknown_agents_filtered,
        # Graph
        test_multi_agent_graph_compiles,
        test_graph_node_count,
    ]

    llm_tests = [
        lambda: test_single_agent_dispatch(args.verbose),
        lambda: test_multi_agent_parallel_dispatch(args.verbose),
        lambda: test_multi_turn_conversation(args.verbose),
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
                name = getattr(test, "__name__", "llm_test")
                print(f"  [FAIL] {name}: {exc}")
                if args.verbose:
                    traceback.print_exc()
                failed += 1
    else:
        print("\n  (Pass --with-llm to run integration tests)")

    _sep()
    print(f"  Results: {passed} passed, {failed} failed")
    _sep()

    if failed:
        raise SystemExit(1)
