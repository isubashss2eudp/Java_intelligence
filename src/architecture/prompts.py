from __future__ import annotations

"""
LLM prompts for the Architecture Understanding Engine.

Each prompt is designed to elicit a structured, grounded response from
the LLM using the architecture report as context. No hallucination of
classes or packages that are not present in the context.
"""

ARCHITECTURE_SYSTEM_PROMPT = """You are a senior Java software architect reviewing a Spring Boot codebase.

You will be given a structured Architecture Report extracted directly from the repository source code.

Rules:
1. Base ALL observations strictly on the provided report data.
2. Never invent class names, package names, or patterns not present in the data.
3. When something is absent from the data, say so explicitly.
4. Use precise technical language appropriate for a senior engineering audience.
5. Format lists with bullet points. Format code references with backticks.
6. Be concise but complete. Aim for clarity over verbosity."""


LAYER_SUMMARY_PROMPT = """Based on the following architecture report, write a concise technical summary
of the layered architecture. Cover:
- How many layers exist and what they are called
- Which packages belong to each layer
- Whether the layering is clean or has violations
- Any unusual patterns in the layer structure

Architecture Report:
{report_text}

Layer Summary:"""


MODULE_SUMMARY_PROMPT = """Based on the following architecture report, describe the module structure:
- How many modules/sub-packages exist
- Whether modules are vertically sliced (controller + service + repo together)
  or horizontally sliced (all controllers in one package, etc.)
- Which modules appear complete vs. incomplete
- Recommendations for module boundary improvements

Architecture Report:
{report_text}

Module Summary:"""


SPRING_PATTERNS_PROMPT = """Based on the following architecture report, describe the Spring Boot patterns detected:
- What Spring stereotypes are used (@Service, @Repository, @RestController, etc.)
- Whether JPA/Hibernate is used and how many entities exist
- Security patterns if present
- Any async or scheduled processing
- Configuration approach

Architecture Report:
{report_text}

Spring Boot Pattern Analysis:"""


ONBOARDING_INTRO_PROMPT = """Write a concise onboarding introduction for a new developer joining this project.

Based on the architecture report below, explain:
1. What this application does (inferred from class names and structure)
2. The overall architectural style (layered, modular, etc.)
3. The main technology stack (Spring Boot version indicators)
4. Where to start reading the code (entry points)
5. The key domain concepts (from entity and service names)

Keep it friendly, practical, and under 300 words.

Architecture Report:
{report_text}

Onboarding Introduction:"""


QUICK_START_PROMPT = """Based on this architecture report, write a practical Quick Start guide for a new developer.

Include:
1. Key entry point classes to read first
2. How a typical HTTP request flows through the codebase
3. The 3-5 most important classes to understand
4. Common patterns used throughout the codebase
5. What to avoid (any anti-patterns if visible from structure)

Architecture Report:
{report_text}

Quick Start Guide:"""


ARCHITECTURE_CRITIQUE_PROMPT = """Perform a critical architecture review based on this report.

Evaluate:
1. Separation of concerns -- are layers clean?
2. Naming consistency -- do class names follow conventions?
3. Module cohesion -- are related classes grouped together?
4. Missing patterns -- what should exist but does not?
5. Potential technical debt visible from structure

Be direct and specific. Point out concrete issues with class/package names from the report.

Architecture Report:
{report_text}

Architecture Critique:"""
