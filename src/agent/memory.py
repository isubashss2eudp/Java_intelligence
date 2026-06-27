from __future__ import annotations
"""
Conversation memory management for the RetroDecrypt Agent.

Uses a sliding window over LangChain message history.
The window is maintained in the LangGraph state (messages list)
so it persists across graph nodes automatically.
"""

from typing import Any, Dict, List, Sequence

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    trim_messages,
)

from src.agent.config import AgentConfig


SYSTEM_CONTENT = """You are the RetroDecrypt Agent -- an expert AI assistant for Java/Spring Boot codebases.

You have access to five specialised tools:
  1. search_repository      -- search source code semantically and by keyword
  2. analyze_dependencies   -- query the class dependency graph
  3. analyze_architecture_tool -- query architectural layers, modules, and Spring patterns
  4. explain_code           -- retrieve and understand a specific class or method
  5. get_documentation      -- retrieve onboarding docs and architectural summaries

How to reason:
- Identify what type of information the question requires (code, dependencies, architecture, docs)
- Choose the most appropriate tool
- If the first tool response is insufficient, call additional tools
- Synthesize a complete, grounded answer citing specific class names and file names
- Never invent class names or behaviour not confirmed by tool results

Citation format: always mention the source file (e.g. CustomerService.java) when referencing code."""


def build_system_message() -> SystemMessage:
    return SystemMessage(content=SYSTEM_CONTENT)


def trim_history(
    messages: List[BaseMessage],
    config: AgentConfig,
) -> List[BaseMessage]:
    """
    Trim the message list to stay within the context window.
    Always preserves the system message and the most recent exchanges.
    """
    if not messages:
        return messages

    # Separate system message
    system = [m for m in messages if isinstance(m, SystemMessage)]
    rest   = [m for m in messages if not isinstance(m, SystemMessage)]

    # Keep last N human+AI turn pairs, plus all tool messages they reference
    window = config.memory_window * 2  # each turn = 1 human + 1 AI minimum
    trimmed = rest[-window:] if len(rest) > window else rest

    return system + trimmed


def format_history_for_display(
    messages: List[BaseMessage],
) -> str:
    """Pretty-print conversation history for debugging."""
    lines = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            lines.append("[System] (omitted)")
        elif isinstance(msg, HumanMessage):
            lines.append(f"[Human] {str(msg.content)[:120]}")
        elif isinstance(msg, AIMessage):
            content = str(msg.content)[:120] if msg.content else "(tool calls)"
            lines.append(f"[Agent] {content}")
        elif isinstance(msg, ToolMessage):
            lines.append(f"[Tool:{msg.name}] {str(msg.content)[:80]}...")
    return chr(10).join(lines)
