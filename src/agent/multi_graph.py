from __future__ import annotations
"""
Multi-Agent LangGraph graph definition.

Graph topology:
                      START
                        |
                   [coordinator]
                   /    |    \    \    \
                  /     |     \    \    \   (parallel via Send)
          [search] [arch] [dep] [docs] [review]
                   \    |    /    /    /
                    [coordinator]  <-- re-enters after each agent reports
                        |
                    (done?)
                        |
                  [synthesizer]
                        |
                       END

Parallel execution:
  When the coordinator returns multiple agents in next_agents, the routing
  function uses LangGraph's Send API to dispatch them simultaneously.
  Their agent_results are merged by the _merge_dicts reducer in the state.

Sequential execution:
  When only one agent is chosen, normal edge routing is used.

Memory:
  The messages list carries full conversation history.
  Each human question appends to the list; the graph returns
  updated state including final_answer.
"""
from typing import List, Union

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from src.agent.config import AgentConfig
from src.agent.state import (
    MultiAgentState,
    AGENT_SEARCH,
    AGENT_ARCHITECTURE,
    AGENT_DEPENDENCY,
    AGENT_DOCS,
    AGENT_REVIEW,
    AGENT_FINISH,
    MAX_ITERATIONS,
)
from src.agent.agents.coordinator import make_coordinator_node, make_synthesizer_node
from src.agent.agents.specialists import (
    make_search_node,
    make_architecture_node,
    make_dependency_node,
    make_docs_node,
    make_review_node,
)


# ---------------------------------------------------------------------------
# Node name constants (used for edges)
# ---------------------------------------------------------------------------

NODE_COORDINATOR  = "coordinator"
NODE_SYNTHESIZER  = "synthesizer"
NODE_SEARCH       = "search_agent"
NODE_ARCHITECTURE = "architecture_agent"
NODE_DEPENDENCY   = "dependency_agent"
NODE_DOCS         = "docs_agent"
NODE_REVIEW       = "review_agent"

_AGENT_TO_NODE = {
    AGENT_SEARCH:       NODE_SEARCH,
    AGENT_ARCHITECTURE: NODE_ARCHITECTURE,
    AGENT_DEPENDENCY:   NODE_DEPENDENCY,
    AGENT_DOCS:         NODE_DOCS,
    AGENT_REVIEW:       NODE_REVIEW,
}


# ---------------------------------------------------------------------------
# Routing function
# ---------------------------------------------------------------------------

def _route_from_coordinator(state: MultiAgentState) -> Union[str, List[Send]]:
    """
    Reads coordinator's next_agents decision and routes accordingly.

    Returns:
      - A single node name string  (sequential)
      - A list of Send objects     (parallel)
      - END literal                (after synthesizer)
    """
    next_agents = state.get("next_agents", [AGENT_FINISH])
    iterations  = state.get("iterations", 0)

    # Force finish on cap
    if iterations >= MAX_ITERATIONS:
        return NODE_SYNTHESIZER

    # Filter to only valid specialist names
    valid = set(_AGENT_TO_NODE.keys())
    specialists = [a for a in next_agents if a in valid]
    wants_finish = AGENT_FINISH in next_agents or not specialists

    if wants_finish:
        return NODE_SYNTHESIZER

    if len(specialists) == 1:
        # Sequential: single specialist
        return _AGENT_TO_NODE[specialists[0]]

    # Parallel: dispatch to multiple specialists simultaneously via Send
    return [Send(_AGENT_TO_NODE[agent], state) for agent in specialists]


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def create_multi_agent(config: AgentConfig | None = None):
    """
    Build and compile the multi-agent LangGraph system.

    Args:
        config: AgentConfig (uses defaults if None).

    Returns:
        Compiled LangGraph CompiledGraph ready for invocation.

    Usage:
        agent = create_multi_agent()
        result = agent.invoke({
            "messages": [HumanMessage("What depends on CustomerRepository?")],
            "query": "What depends on CustomerRepository?",
            "agent_results": {},
            "next_agents": [],
            "active_agents": [],
            "iterations": 0,
            "final_answer": "",
            "task_context": "",
        })
        print(result["final_answer"])
    """
    if config is None:
        config = AgentConfig()

    # Load LLM (inherits proxy and model config from llm.py)
    from src.llm import load_llm
    llm = load_llm()

    # Instantiate all agent nodes
    coordinator_node  = make_coordinator_node(llm)
    synthesizer_node  = make_synthesizer_node(llm)
    search_node       = make_search_node(llm)
    architecture_node = make_architecture_node(llm)
    dependency_node   = make_dependency_node(llm)
    docs_node         = make_docs_node(llm)
    review_node       = make_review_node(llm)

    # Build the StateGraph
    workflow = StateGraph(MultiAgentState)

    # Register all nodes
    workflow.add_node(NODE_COORDINATOR,  coordinator_node)
    workflow.add_node(NODE_SYNTHESIZER,  synthesizer_node)
    workflow.add_node(NODE_SEARCH,       search_node)
    workflow.add_node(NODE_ARCHITECTURE, architecture_node)
    workflow.add_node(NODE_DEPENDENCY,   dependency_node)
    workflow.add_node(NODE_DOCS,         docs_node)
    workflow.add_node(NODE_REVIEW,       review_node)

    # Entry point
    workflow.set_entry_point(NODE_COORDINATOR)

    # Coordinator routes to specialists (sequential or parallel)
    workflow.add_conditional_edges(
        NODE_COORDINATOR,
        _route_from_coordinator,
        {
            NODE_SEARCH:       NODE_SEARCH,
            NODE_ARCHITECTURE: NODE_ARCHITECTURE,
            NODE_DEPENDENCY:   NODE_DEPENDENCY,
            NODE_DOCS:         NODE_DOCS,
            NODE_REVIEW:       NODE_REVIEW,
            NODE_SYNTHESIZER:  NODE_SYNTHESIZER,
        },
    )

    # All specialists route back to coordinator after completing
    for node_name in [NODE_SEARCH, NODE_ARCHITECTURE, NODE_DEPENDENCY,
                      NODE_DOCS, NODE_REVIEW]:
        workflow.add_edge(node_name, NODE_COORDINATOR)

    # Synthesizer -> END
    workflow.add_edge(NODE_SYNTHESIZER, END)

    return workflow.compile()
