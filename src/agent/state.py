from __future__ import annotations
"""
Shared state definition for the Multi-Agent RetroDecrypt System.

Every node in the graph reads from and writes to MultiAgentState.
The `agent_results` field uses a merge reducer so parallel agents
can write their outputs simultaneously without overwriting each other.
"""
from typing import Annotated, Dict, List, Optional, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


def _merge_dicts(a: Dict, b: Dict) -> Dict:
    """Reducer: merge two dicts, b values overwrite a on key collision."""
    return {**a, **b}


class MultiAgentState(TypedDict):
    """
    Shared state threaded through all nodes in the multi-agent graph.

    Fields:
        messages:       Full conversation history (system + human + AI + tool).
                        `add_messages` reducer appends rather than replaces.

        query:          Original user query string.  Preserved unmodified
                        throughout the entire agent execution so every
                        specialist sees the original intent.

        active_agents:  Names of agents currently being invoked (used for
                        display and loop-prevention).

        agent_results:  Dict[agent_name -> result_text].  Each specialist
                        writes its output here.  `_merge_dicts` reducer
                        enables safe concurrent writes during parallel
                        execution via the Send API.

        next_agents:    List of agent names the coordinator wants to call
                        next.  Empty list or ["FINISH"] triggers synthesis.

        iterations:     Safety counter -- coordinator increments this on
                        every routing decision.  Graph halts at MAX_ITER.

        final_answer:   The synthesized answer assembled by the coordinator
                        after all required specialists have reported.

        task_context:   Free-form text the coordinator passes to specialists
                        to scope their work (e.g. "focus on OrderService").
    """
    messages:      Annotated[Sequence[BaseMessage], add_messages]
    query:         str
    active_agents: List[str]
    agent_results: Annotated[Dict[str, str], _merge_dicts]
    next_agents:   List[str]
    iterations:    int
    final_answer:  str
    task_context:  str


MAX_ITERATIONS = 8   # hard cap on coordinator cycles

# Canonical agent names used throughout the system
AGENT_SEARCH        = "search"
AGENT_ARCHITECTURE  = "architecture"
AGENT_DEPENDENCY    = "dependency"
AGENT_DOCS          = "docs"
AGENT_REVIEW        = "review"
AGENT_FINISH        = "FINISH"

ALL_AGENT_NAMES = [
    AGENT_SEARCH,
    AGENT_ARCHITECTURE,
    AGENT_DEPENDENCY,
    AGENT_DOCS,
    AGENT_REVIEW,
]
