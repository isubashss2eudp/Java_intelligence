from __future__ import annotations

"""
LLM prompts and response parsers for Phase 8 Code Review Intelligence.

The LLM deep-review pass takes the top CRITICAL/HIGH static findings and
enriches them with nuanced reasoning and discovers additional issues that
purely regex-based analysis would miss (e.g. incorrect business logic,
subtle Spring Boot anti-patterns, missing edge case handling).
"""

import json
import re
from typing import Dict, List

from src.code_review.models import FindingCategory, ReviewFinding, Severity


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_llm_review_prompt(
    high_priority_findings: List[ReviewFinding],
    class_snippets: Dict[str, str],
) -> str:
    """
    Build a structured LLM prompt for the deep-review pass.

    Args:
        high_priority_findings: CRITICAL/HIGH findings from static analysis.
        class_snippets:         {class_name -> source_code_snippet}.

    Returns:
        Prompt string ready for LLM invocation.
    """
    findings_text = "\n".join(
        f"  [{f.rule_id}] [{f.severity.value.upper()}] {f.title}\n"
        f"  Description: {f.description[:300]}\n"
        f"  Classes: {', '.join(f.affected_classes[:3])}"
        for f in high_priority_findings
    )

    snippets_text = "\n\n".join(
        f"=== {cls} ===\n{code[:2000]}"
        for cls, code in class_snippets.items()
    )

    return f"""You are a senior Java/Spring Boot architect performing a deep code review.

STATIC ANALYSIS FINDINGS (already identified):
{findings_text}

SOURCE CODE SNIPPETS:
{snippets_text}

TASK:
1. Review the source code snippets above.
2. Confirm, add context to, or refine the static analysis findings.
3. Identify any ADDITIONAL issues the static analyser may have missed:
   - Incorrect Spring transaction boundaries
   - Missing null checks or edge case handling
   - Incorrect use of Spring Data JPA
   - Thread safety issues
   - Incorrect error propagation
   - Business logic errors visible from the code

OUTPUT FORMAT (respond with valid JSON only, no markdown, no explanation):
{{
  "additional_findings": [
    {{
      "rule_id": "LLM-001",
      "category": "security|solid|performance|maintainability|design_pattern|tech_debt",
      "severity": "critical|high|medium|low|info",
      "title": "Short title (< 80 chars)",
      "description": "Detailed description of the issue.",
      "recommendation": "Concrete fix recommendation.",
      "affected_classes": ["ClassName"],
      "evidence": "Specific code evidence (optional)"
    }}
  ]
}}

Return only the JSON object. Do not include findings already listed above unless
you have significant additional context to add."""


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def parse_llm_findings(raw_text: str) -> List[ReviewFinding]:
    """
    Parse LLM JSON response into ReviewFinding instances.

    Gracefully handles malformed JSON or unexpected structure.
    """
    # Extract JSON block from response (LLM may add surrounding text)
    json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if not json_match:
        return []

    try:
        data = json.loads(json_match.group())
        additional = data.get("additional_findings", [])
    except (json.JSONDecodeError, ValueError):
        return []

    findings = []
    for item in additional:
        try:
            category = FindingCategory(item.get("category", "maintainability"))
            severity = Severity(item.get("severity", "info"))
            findings.append(ReviewFinding(
                category=category,
                severity=severity,
                rule_id=item.get("rule_id", "LLM-000"),
                title=item.get("title", "LLM finding"),
                description=item.get("description", ""),
                recommendation=item.get("recommendation", ""),
                affected_classes=item.get("affected_classes", []),
                evidence=item.get("evidence", ""),
            ))
        except (ValueError, KeyError):
            continue  # Skip malformed entries

    return findings


# ---------------------------------------------------------------------------
# Focused class review prompt
# ---------------------------------------------------------------------------

FOCUSED_CLASS_REVIEW_PROMPT = """You are a senior Java/Spring Boot code reviewer.

Review the following Java class and provide a comprehensive assessment.

Class: {class_name}
Source code:
```java
{source_code}
```

Analyse the following dimensions:
1. SOLID Principles adherence (SRP, OCP, LSP, ISP, DIP)
2. Design patterns correctly applied or anti-patterns present
3. Security vulnerabilities (OWASP Top 10 relevant issues)
4. Performance concerns (N+1 queries, missing transactions, eager loading, etc.)
5. Maintainability (complexity, naming, documentation, error handling)
6. Technical debt (TODO comments, deprecated usage, hardcoded values)

Additional context:
- Repository type: Java/Spring Boot
- Layer: {layer}
- Dependencies: {dependencies}

Provide findings in JSON format:
{{
  "findings": [
    {{
      "category": "solid|security|performance|maintainability|design_pattern|tech_debt",
      "severity": "critical|high|medium|low|info",
      "title": "...",
      "description": "...",
      "recommendation": "...",
      "evidence": "specific line or code snippet"
    }}
  ],
  "overall_assessment": "Brief paragraph on overall class quality",
  "grade": "A|B|C|D|F"
}}"""
