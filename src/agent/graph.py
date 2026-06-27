from __future__ import annotations
"""
LangGraph agent graph definition.

Architecture: ReAct (Reason + Act) pattern with tool use.

Graph structure:
  START
    |
    v
  [agent]  <---- calls LLM with tools bound
    |              |
    |-- tool calls --> [tools]  <-- executes chosen tool
    |              |
    |<--- tool results ----------|
    |
    |-- "end" --> END  (when LLM produces final answer)

Memory: messages list in AgentState carries full conversation history.
Trimming is applied before each LLM call to stay within context window.
"""

from typing import Annotated, Literal, Sequence

from langchain_core.messages import BaseMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from src.agent.config import AgentConfig
from src.agent.memory import build_system_message, trim_history
from src.agent.tools import ALL_TOOLS


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """
    LangGraph state for the RetroDecrypt Agent.

    messages: full conversation history (system + human + AI + tool results).
              `add_messages` reducer appends new messages rather than replacing.
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]


# ---------------------------------------------------------------------------
# Node: agent (LLM reasoning)
# ---------------------------------------------------------------------------

def _make_agent_node(llm, config: AgentConfig):
    """
    Returns the agent node function.
    The LLM has all tools bound and can choose which to call.
    """

    def agent_node(state: AgentState) -> dict:
        messages = list(state["messages"])

        # Ensure system message is first
        if not messages or not hasattr(messages[0], "content"):
            messages = [build_system_message()] + messages
        elif messages[0].type != "system":
            messages = [build_system_message()] + messages

        # Trim to stay within context window
        messages = trim_history(messages, config)

        response = llm.invoke(messages)
        return {"messages": [response]}

    return agent_node


# ---------------------------------------------------------------------------
# Routing: continue to tools or end?
# ---------------------------------------------------------------------------

def _should_continue(state: AgentState) -> Literal["tools", "end"]:
    """
    If the last AI message contains tool calls -> route to tools.
    Otherwise -> end (final answer ready).
    """
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "end"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def create_agent(config: AgentConfig | None = None):
    """
    Build and compile the LangGraph ReAct agent.

    Returns a compiled LangGraph app that can be invoked with:
        result = agent.invoke({"messages": [HumanMessage("your question")]})

    Args:
        config: AgentConfig instance. Uses defaults if None.

    Returns:
        Compiled LangGraph CompiledGraph.
    """
    if config is None:
        config = AgentConfig()

    # Load LLM with tools bound
    from src.llm import load_llm
    base_llm = load_llm()
    llm = base_llm.bind_tools(ALL_TOOLS)

    # Build graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent", _make_agent_node(llm, config))
    workflow.add_node("tools", ToolNode(ALL_TOOLS))

    # Set entry point
    workflow.set_entry_point("agent")

    # Conditional routing from agent node
    workflow.add_conditional_edges(
        "agent",
        _should_continue,
        {"tools": "tools", "end": END},
    )

    # After tools, always return to agent for next reasoning step
    workflow.add_edge("tools", "agent")

    return workflow.compile()
