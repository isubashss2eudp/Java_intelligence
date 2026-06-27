from __future__ import annotations
"""
Specialist agent node factory functions.

Each specialist:
  - Has a focused system prompt scoping its expertise.
  - Has access only to the tools relevant to its domain.
  - Executes up to MAX_TOOL_CALLS tool invocations per invocation.
  - Writes its result to agent_results[agent_name] in the shared state.
  - Always returns control to the coordinator after completing.

Specialists:
  make_search_node        -- Repository Search Agent
  make_architecture_node  -- Architecture Analysis Agent
  make_dependency_node    -- Dependency Graph Agent
  make_docs_node          -- Documentation Agent
  make_review_node        -- Code Review Agent (Phase 6 + Phase 8 tools)
"""


from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agent.state import MultiAgentState
from src.agent.tools import (
    search_repository,
    analyze_architecture_tool,
    analyze_dependencies,
    explain_code,
    get_documentation,
    # Phase 8 tools
    review_code_quality,
    analyze_solid_principles,
    detect_security_issues,
    analyze_technical_debt,
)

# Maximum tool call rounds per specialist invocation
MAX_TOOL_CALLS = 5


# ---------------------------------------------------------------------------
# Internal: run a ReAct loop for one specialist
# ---------------------------------------------------------------------------

def _run_specialist(
    llm_with_tools,
    system_prompt: str,
    query: str,
    task_context: str,
    tool_map: Dict[str, Any],
    agent_name: str,
) -> str:
    """
    Run a focused ReAct loop for a single specialist agent.

    Args:
        llm_with_tools : LLM with relevant tools bound.
        system_prompt  : Specialist system prompt.
        query          : Original user query.
        task_context   : Coordinator scoping instruction.
        tool_map       : {tool_name -> callable} for this specialist.
        agent_name     : For error messages.

    Returns:
        Text result from the specialist (tool outputs + final reasoning).
    """
    focus = task_context or query
    user_msg = (
        f"User question: {query}" + "\n\n"
        + (f"Focus: {task_context}" + "\n\n" if task_context else "")
        + "Use your tools to gather the information needed, then summarise your findings."
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_msg),
    ]

    collected_tool_outputs = []

    for _ in range(MAX_TOOL_CALLS):
        try:
            response = llm_with_tools.invoke(messages)
        except Exception as exc:
            return f"[{agent_name}] LLM error: {exc}"

        messages.append(response)

        # No tool calls -> agent is done
        if not getattr(response, "tool_calls", None):
            break

        # Execute each tool call
        for tc in response.tool_calls:
            tool_name = tc["name"]
            tool_args = tc.get("args", {})
            tool_fn   = tool_map.get(tool_name)

            if tool_fn is None:
                tool_output = f"Unknown tool: {tool_name}"
            else:
                try:
                    tool_output = tool_fn.invoke(tool_args)
                except Exception as exc:
                    tool_output = f"Tool error ({tool_name}): {exc}"

            collected_tool_outputs.append(f"[{tool_name}]: {tool_output[:1500]}")
            messages.append(ToolMessage(
                content=tool_output,
                tool_call_id=tc["id"],
                name=tool_name,
            ))

    # Extract final text answer from last AI message
    final_text = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            final_text = str(msg.content)
            break

    if not final_text and collected_tool_outputs:
        final_text = "Tool results gathered:" + "\n" + "\n\n".join(collected_tool_outputs)

    return final_text or f"[{agent_name}] No results produced."


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_SEARCH_SYSTEM = """You are the Repository Search Agent for a Java/Spring Boot codebase.

Your role: find relevant source code using semantic and keyword search.

Guidelines:
- Use the search_repository tool to find code snippets
- If the first search is too broad, refine with more specific queries
- Always note the file name and class name when referencing code
- Quote actual code from the search results to support your findings
- Summarise what the code does, not just where it is found"""


_ARCHITECTURE_SYSTEM = """You are the Architecture Analysis Agent for a Java/Spring Boot codebase.

Your role: analyse architectural layers, modules, Spring patterns, and structural health.

Guidelines:
- Use analyze_architecture_tool with appropriate aspects (summary, layers, modules, spring_patterns, roles, health)
- Start with 'summary' for broad questions, then drill into specific aspects
- Identify layer violations, orphan modules, or Spring anti-patterns if present
- Relate findings back to the user's question clearly
- Express architectural concerns in terms of maintainability and scalability"""


_DEPENDENCY_SYSTEM = """You are the Dependency Graph Agent for a Java/Spring Boot codebase.

Your role: query and explain class dependency relationships.

Guidelines:
- Use analyze_dependencies with query_type: who_depends_on, get_dependencies,
  dependency_chain, cycles, most_depended_on, orphans, stats, or by_type
- For "what depends on X" -> use who_depends_on
- For "what does X depend on" -> use get_dependencies
- For "how are A and B connected" -> use dependency_chain
- Always check for cycles when asked about dependencies broadly
- Express coupling in terms of risk and architectural impact"""


_DOCS_SYSTEM = """You are the Documentation Agent for a Java/Spring Boot codebase.

Your role: retrieve and present onboarding documentation.

Guidelines:
- Use get_documentation with appropriate sections: overview, quick_start,
  request_flow, layers, modules, spring, diagrams, or full
- For "how do I start" -> use quick_start
- For "what is the request flow" -> use request_flow
- For "what is this project" -> use overview
- Present documentation in a developer-friendly format
- Suggest next steps when appropriate"""


_REVIEW_SYSTEM = """You are the Code Review Intelligence Agent for a Java/Spring Boot codebase (Phase 8).

Your role: deliver comprehensive, production-grade code review using static analysis tools
and deep reasoning about code quality, security, and maintainability.

Tools available and when to use them:
  review_code_quality      -- Full review across ALL categories (SOLID, security, performance,
                              maintainability, duplicates, tech_debt, patterns). Use for broad
                              "review this codebase" or "assess code quality" questions.
  analyze_solid_principles -- Focused SOLID principles analysis. Use for "does this follow SOLID?",
                              "is SRP violated?", dependency injection questions.
  detect_security_issues   -- Security vulnerability scan (OWASP Top 10). Use for "any security
                              issues?", "hardcoded credentials?", "SQL injection risk?" questions.
  analyze_technical_debt   -- Tech debt + duplicate code. Use for "technical debt", "TODO comments",
                              "missing tests", "duplicate code" questions.
  search_repository        -- Fetch actual source code for deeper analysis. Use to supplement
                              tool findings with actual code context.
  explain_code             -- Deep-dive into a specific class/method.

Review workflow:
  1. For a specific class: use review_code_quality(target_class="ClassName") first.
  2. For a specific concern: use the focused tool (detect_security_issues, analyze_solid_principles).
  3. For confirmation: use search_repository to read actual code evidence.
  4. Always summarise findings by severity: CRITICAL → HIGH → MEDIUM → LOW.
  5. Provide concrete, actionable recommendations for every finding.
  6. Distinguish bugs (must fix) from code smells (should fix) from style (nice to fix).

Output format:
  - Start with quality score and grade
  - List CRITICAL and HIGH findings with specific remediation
  - Summarise patterns/anti-patterns detected
  - Close with top 3 actionable recommendations"""


# ---------------------------------------------------------------------------
# Specialist node factories
# ---------------------------------------------------------------------------

def make_search_node(llm):
    """Repository Search Agent -- searches source code semantically."""
    tool_map = {"search_repository": search_repository}
    bound_llm = llm.bind_tools([search_repository])

    def search_agent(state: MultiAgentState) -> dict:
        result = _run_specialist(
            llm_with_tools=bound_llm,
            system_prompt=_SEARCH_SYSTEM,
            query=state.get("query", ""),
            task_context=state.get("task_context", ""),
            tool_map=tool_map,
            agent_name="search",
        )
        return {"agent_results": {"search": result}}

    return search_agent


def make_architecture_node(llm):
    """Architecture Agent -- analyses layers, modules, Spring patterns."""
    tool_map = {"analyze_architecture_tool": analyze_architecture_tool}
    bound_llm = llm.bind_tools([analyze_architecture_tool])

    def architecture_agent(state: MultiAgentState) -> dict:
        result = _run_specialist(
            llm_with_tools=bound_llm,
            system_prompt=_ARCHITECTURE_SYSTEM,
            query=state.get("query", ""),
            task_context=state.get("task_context", ""),
            tool_map=tool_map,
            agent_name="architecture",
        )
        return {"agent_results": {"architecture": result}}

    return architecture_agent


def make_dependency_node(llm):
    """Dependency Agent -- queries class dependency graph."""
    tool_map = {"analyze_dependencies": analyze_dependencies}
    bound_llm = llm.bind_tools([analyze_dependencies])

    def dependency_agent(state: MultiAgentState) -> dict:
        result = _run_specialist(
            llm_with_tools=bound_llm,
            system_prompt=_DEPENDENCY_SYSTEM,
            query=state.get("query", ""),
            task_context=state.get("task_context", ""),
            tool_map=tool_map,
            agent_name="dependency",
        )
        return {"agent_results": {"dependency": result}}

    return dependency_agent


def make_docs_node(llm):
    """Documentation Agent -- retrieves onboarding documentation."""
    tool_map = {"get_documentation": get_documentation}
    bound_llm = llm.bind_tools([get_documentation])

    def docs_agent(state: MultiAgentState) -> dict:
        result = _run_specialist(
            llm_with_tools=bound_llm,
            system_prompt=_DOCS_SYSTEM,
            query=state.get("query", ""),
            task_context=state.get("task_context", ""),
            tool_map=tool_map,
            agent_name="docs",
        )
        return {"agent_results": {"docs": result}}

    return docs_agent


def make_review_node(llm):
    """Code Review Intelligence Agent (Phase 8) -- full static analysis + reasoning."""
    tools = [
        review_code_quality,
        analyze_solid_principles,
        detect_security_issues,
        analyze_technical_debt,
        search_repository,
        explain_code,
    ]
    tool_map = {
        "review_code_quality":      review_code_quality,
        "analyze_solid_principles": analyze_solid_principles,
        "detect_security_issues":   detect_security_issues,
        "analyze_technical_debt":   analyze_technical_debt,
        "search_repository":        search_repository,
        "explain_code":             explain_code,
    }
    bound_llm = llm.bind_tools(tools)

    def review_agent(state: MultiAgentState) -> dict:
        result = _run_specialist(
            llm_with_tools=bound_llm,
            system_prompt=_REVIEW_SYSTEM,
            query=state.get("query", ""),
            task_context=state.get("task_context", ""),
            tool_map=tool_map,
            agent_name="review",
        )
        return {"agent_results": {"review": result}}

    return review_agent
