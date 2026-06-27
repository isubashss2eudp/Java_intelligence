from __future__ import annotations
"""
Coordinator Agent -- the supervisor of the multi-agent system.

Responsibilities:
  1. Classify the user query and decide which specialist agent(s) to invoke.
  2. Optionally invoke multiple agents in parallel when the query spans domains.
  3. After agents report back, evaluate whether the collected results are
     sufficient to answer the user, or whether further agents are needed.
  4. Synthesize a final, grounded answer from all collected agent results.

The coordinator uses structured output (Pydantic model) for routing so the
LLM's routing decision is always type-safe and parseable.
"""


from typing import List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agent.state import (
    MultiAgentState,
    ALL_AGENT_NAMES,
    AGENT_FINISH,
    MAX_ITERATIONS,
)


# ---------------------------------------------------------------------------
# Structured output model for routing
# ---------------------------------------------------------------------------

class RoutingDecision(BaseModel):
    """
    The coordinator LLM returns this model to decide next steps.
    Using structured output ensures the routing is always parseable.
    """
    next_agents: List[str] = Field(
        description=(
            "List of specialist agent names to call next. "
            "Valid values: search, architecture, dependency, docs, review. "
            "Use multiple for parallel execution. "
            "Use ['FINISH'] when collected results are sufficient to answer."
        )
    )
    reasoning: str = Field(
        description="Brief explanation of why these agents were chosen."
    )
    task_context: str = Field(
        default="",
        description=(
            "Optional scoping instruction passed to specialists, e.g. "
            "'focus on OrderService' or 'look for circular dependencies only'."
        )
    )


# ---------------------------------------------------------------------------
# Coordinator system prompt
# ---------------------------------------------------------------------------

COORDINATOR_SYSTEM = """You are the Coordinator of a multi-agent Java repository intelligence system.

You receive questions about a Java/Spring Boot codebase and route them to specialist agents.

Specialist agents available:
  search       -- searches source code; use for "how does X work", "show me Y class"
  architecture -- queries layer/module/Spring Boot patterns; use for structural questions
  dependency   -- queries the dependency graph; use for "what depends on X", cycles, chains
  docs         -- retrieves onboarding documentation; use for getting-started questions
  review       -- Phase 8 Code Review Intelligence: SOLID analysis, security vulnerabilities,
                  performance issues, maintainability metrics, duplicate code detection,
                  technical debt; use for ANY code quality, review, or audit question

Routing rules:
  1. Choose the MINIMUM set of agents needed to answer the question.
  2. Call multiple agents IN PARALLEL when the question spans multiple domains.
  3. After agents report back, check if their results fully answer the question.
     If yes -> return ["FINISH"].
     If no  -> route to additional agents with narrowed task_context.
  4. Never call the same agent twice with the same task_context.
  5. If iterations exceed 6, return ["FINISH"] regardless.

Examples:
  "What does CustomerService do?"                  -> ["search"]
  "What layers exist and any circular deps?"        -> ["architecture", "dependency"]  (parallel)
  "How do I onboard to this project?"               -> ["docs"]
  "Review OrderService for SOLID violations"        -> ["review"]
  "Any security issues in the codebase?"            -> ["review"]
  "What is the technical debt?"                     -> ["review"]
  "Find duplicate code"                             -> ["review"]
  "What depends on CustomerRepository?"             -> ["dependency"]
  "Review architecture and identify security risks" -> ["architecture", "review"]  (parallel)"""


# ---------------------------------------------------------------------------
# Synthesizer system prompt
# ---------------------------------------------------------------------------

SYNTHESIZER_SYSTEM = """You are a senior Java architect synthesizing findings from multiple specialist agents.

You have received analysis from one or more specialist agents about a Java/Spring Boot codebase.

Your task:
  1. Integrate all agent findings into a single, coherent answer.
  2. Eliminate redundancy -- do not repeat the same fact twice.
  3. Always cite specific class names, file names, and package names from the results.
  4. Clearly distinguish between findings from different domains (code, architecture, dependencies).
  5. Structure the answer logically: start with the direct answer, then supporting details.
  6. If agents found conflicting or incomplete information, say so explicitly.
  7. Never invent information not present in the agent results."""


# ---------------------------------------------------------------------------
# Coordinator node function
# ---------------------------------------------------------------------------

def make_coordinator_node(llm):
    """
    Returns the coordinator node function bound to the given LLM.
    The LLM is configured with structured output (RoutingDecision).
    """
    router_llm = llm.with_structured_output(RoutingDecision)

    def coordinator(state: MultiAgentState) -> dict:
        query      = state.get("query", "")
        results    = state.get("agent_results", {})
        iterations = state.get("iterations", 0)

        # Force finish if iteration cap reached
        if iterations >= MAX_ITERATIONS:
            return {
                "next_agents": [AGENT_FINISH],
                "iterations":  iterations + 1,
                "task_context": "",
            }

        # Build context summary of what agents have already reported
        if results:
            collected = "\n\n".join(
                f"=== {name.upper()} AGENT RESULT ===" + "\n" + text
                for name, text in results.items()
            )
            user_content = (
                f"Original question: {query}" + "\n\n"
                f"Agent results collected so far:" + "\n" + collected + "\n\n"
                "Based on these results, decide: route to more agents or FINISH?"
            )
        else:
            user_content = f"New question: {query}" + "\n\nNo agents have run yet. Decide which to call first."

        messages = [
            SystemMessage(content=COORDINATOR_SYSTEM),
            HumanMessage(content=user_content),
        ]

        try:
            decision: RoutingDecision = router_llm.invoke(messages)
            next_agents  = decision.next_agents or [AGENT_FINISH]
            task_context = decision.task_context or ""
        except Exception as exc:
            # Fallback: try all-rounder if structured output fails
            next_agents  = [AGENT_FINISH]
            task_context = f"(routing error: {exc})"

        # Validate agent names
        valid = set(ALL_AGENT_NAMES) | {AGENT_FINISH}
        next_agents = [a for a in next_agents if a in valid] or [AGENT_FINISH]

        return {
            "next_agents":   next_agents,
            "task_context":  task_context,
            "iterations":    iterations + 1,
            "active_agents": next_agents,
        }

    return coordinator


# ---------------------------------------------------------------------------
# Synthesizer node function
# ---------------------------------------------------------------------------

def make_synthesizer_node(llm):
    """
    Returns the synthesizer node that produces the final answer.
    Called once the coordinator decides no more agents are needed.
    """

    def synthesizer(state: MultiAgentState) -> dict:
        query   = state.get("query", "")
        results = state.get("agent_results", {})

        if not results:
            return {
                "final_answer": "No information was gathered. Please try a more specific question.",
                "messages": [AIMessage(content="No information gathered.")],
            }

        collected = "\n\n".join(
            f"--- {name.upper()} AGENT ---" + "\n" + text
            for name, text in results.items()
        )

        prompt = (
            f"Question: {query}" + "\n\n"
            f"Specialist Agent Results:" + "\n" + collected + "\n\n"
            "Synthesize a complete, grounded answer:"
        )

        messages = [
            SystemMessage(content=SYNTHESIZER_SYSTEM),
            HumanMessage(content=prompt),
        ]

        try:
            response  = llm.invoke(messages)
            answer    = getattr(response, "content", str(response)) or "No answer generated."
        except Exception as exc:
            answer = (
                "Synthesis error: " + str(exc) + "\n\n"
                "Raw agent results:" + "\n" + collected
            )

        return {
            "final_answer": answer,
            "messages":     [AIMessage(content=answer)],
        }

    return synthesizer
