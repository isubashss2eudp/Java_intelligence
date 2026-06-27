from __future__ import annotations
"""
RetroDecrypt Agent system.

Single-agent (Phase 6):
    from src.agent import create_agent, AgentConfig
    agent = create_agent()
    result = agent.invoke({"messages": [HumanMessage("...")]})

Multi-agent (Phase 7):
    from src.agent import create_multi_agent, AgentConfig, initial_state
    agent = create_multi_agent()
    result = agent.invoke(initial_state("What depends on CustomerRepository?"))
    print(result["final_answer"])
"""
from src.agent.graph import create_agent
from src.agent.multi_graph import create_multi_agent
from src.agent.config import AgentConfig
from src.agent.state import MultiAgentState


def initial_state(query: str) -> dict:
    """
    Build the initial MultiAgentState dict for a new user query.
    Use this as the input to create_multi_agent().invoke().

    Args:
        query: The user's question string.

    Returns:
        Dict suitable for multi-agent graph invocation.
    """
    from langchain_core.messages import HumanMessage
    return {
        "messages":      [HumanMessage(content=query)],
        "query":         query,
        "agent_results": {},
        "next_agents":   [],
        "active_agents": [],
        "iterations":    0,
        "final_answer":  "",
        "task_context":  "",
    }


__all__ = [
    "create_agent",
    "create_multi_agent",
    "AgentConfig",
    "MultiAgentState",
    "initial_state",
]
