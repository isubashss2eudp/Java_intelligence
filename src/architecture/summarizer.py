from __future__ import annotations

"""
LLM-powered architecture summarizer.

Generates narrative descriptions of the architecture using the LLM.
Falls back gracefully to template-based summaries when the LLM is
unavailable (no API key, quota exhausted, network blocked).
"""

from typing import Dict, Optional

from src.architecture.analyzer import ArchitectureReport
from src.architecture.detector import ROLE_LABELS
from src.architecture.prompts import (
    ARCHITECTURE_SYSTEM_PROMPT,
    LAYER_SUMMARY_PROMPT,
    MODULE_SUMMARY_PROMPT,
    SPRING_PATTERNS_PROMPT,
    ONBOARDING_INTRO_PROMPT,
    QUICK_START_PROMPT,
    ARCHITECTURE_CRITIQUE_PROMPT,
)


# ---------------------------------------------------------------------------
# Report serialisation (compact text for LLM context)
# ---------------------------------------------------------------------------

def _report_to_text(report: ArchitectureReport) -> str:
    """Convert ArchitectureReport to a compact text suitable for LLM context."""
    lines = [
        f"Base Package: {report.base_package or 'unknown'}",
        f"Total Classes: {report.stats.get('total_classes', 0)}",
        "",
        "Layers:",
    ]
    for layer in report.layers:
        if layer.class_count > 0:
            class_names = ", ".join(c.class_name for c in layer.classes[:8])
            if len(layer.classes) > 8:
                class_names += f" (+{len(layer.classes) - 8} more)"
            lines.append(f"  {layer.name} ({layer.class_count}): {class_names}")

    lines.append("")
    lines.append("Modules:")
    for mod in report.modules:
        lines.append(
            f"  {mod.name}: {len(mod.classes)} classes "
            f"[{', '.join(mod.roles_present)}] "
            f"{'(full-stack)' if mod.is_full_stack else ''}"
        )

    lines.append("")
    lines.append("Spring Boot Patterns:")
    for p in report.spring_patterns.patterns_detected:
        lines.append(f"  - {p}")

    lines.append("")
    lines.append("Role Breakdown:")
    for role, classes in sorted(
        report.roles_by_name.items(), key=lambda x: -len(x[1])
    ):
        if role != "unknown" and classes:
            label = ROLE_LABELS.get(role, role)
            names = ", ".join(c.class_name for c in classes[:5])
            if len(classes) > 5:
                names += f" (+{len(classes) - 5} more)"
            lines.append(f"  {label}: {names}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Template fallback (no LLM required)
# ---------------------------------------------------------------------------

def _template_summaries(report: ArchitectureReport) -> Dict[str, str]:
    """
    Generate structured template-based summaries without using an LLM.
    Used as fallback when the LLM is unavailable.
    """
    summaries: Dict[str, str] = {}

    # Layer summary
    populated = [l for l in report.layers if l.class_count > 0]
    layer_names = [l.name for l in populated]
    summaries["layer_summary"] = (
        f"The application uses a {len(populated)}-layer architecture: "
        + ", ".join(layer_names) + ". "
        + f"The presentation layer contains {len(report.roles_by_name.get('controller', []))} "
        + f"controller(s), the business layer has {len(report.roles_by_name.get('service', []))} "
        + f"service(s), and the persistence layer exposes "
        + f"{len(report.roles_by_name.get('repository', []))} repository/repositories."
    )

    # Module summary
    if report.modules:
        full_stack = [m for m in report.modules if m.is_full_stack]
        summaries["module_summary"] = (
            f"{len(report.modules)} module(s) detected. "
            + (f"{len(full_stack)} are full-stack (controller + service + repository). " if full_stack else "")
            + "Modules: " + ", ".join(m.name for m in report.modules[:8]) + "."
        )
    else:
        summaries["module_summary"] = (
            "No distinct feature modules detected. "
            "The codebase appears to use a flat, role-based package structure "
            "(all controllers in one package, all services in another)."
        )

    # Spring patterns
    patterns = report.spring_patterns.patterns_detected
    summaries["spring_patterns"] = (
        "Spring Boot patterns detected: " + "; ".join(patterns) + "."
        if patterns else
        "No specific Spring Boot patterns detected."
    )

    # Onboarding intro
    entry = report.spring_patterns.entry_point_class or "the main Application class"
    controllers = report.roles_by_name.get("controller", [])
    services = report.roles_by_name.get("service", [])
    summaries["onboarding_intro"] = (
        f"This is a Spring Boot application (entry point: {entry}) with "
        f"{report.stats.get('total_classes', 0)} Java classes. "
        f"Start by reading {controllers[0].class_name if controllers else 'the controllers'} "
        f"to understand the API surface, then trace through "
        f"{services[0].class_name if services else 'the services'} "
        f"for business logic. "
        f"The codebase follows a standard layered architecture with "
        + ", ".join(l.name for l in populated[:3]) + " layers."
    )

    # Quick start
    entry_points = []
    for role in ("main", "controller", "service"):
        classes = report.roles_by_name.get(role, [])
        if classes:
            entry_points.append(f"{role}: {classes[0].class_name}")
    summaries["quick_start"] = (
        "Key entry points: " + "; ".join(entry_points) + ". "
        "Trace a request from Controller -> Service -> Repository to understand the data flow."
    )

    # Critique
    issues = []
    unknown = report.roles_by_name.get("unknown", [])
    if unknown:
        issues.append(
            f"{len(unknown)} unclassified class(es) -- consider adding Spring stereotypes "
            + f"or renaming: {', '.join(c.class_name for c in unknown[:3])}"
        )
    if not report.modules:
        issues.append(
            "No feature modules detected -- consider organising by feature "
            "(order/, customer/, etc.) rather than by role."
        )
    summaries["critique"] = (
        "Architecture issues found: " + "; ".join(issues)
        if issues else
        "No major architectural issues detected from static analysis."
    )

    return summaries


# ---------------------------------------------------------------------------
# LLM-powered summaries
# ---------------------------------------------------------------------------

def _llm_summary(llm, system: str, prompt: str) -> Optional[str]:
    """Call the LLM and return the text content, or None on failure."""
    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        response = llm.invoke([
            SystemMessage(content=system),
            HumanMessage(content=prompt),
        ])
        content = getattr(response, "content", None)
        return content if content else None
    except Exception:
        return None


def summarize_architecture(
    report: ArchitectureReport,
    llm=None,
) -> Dict[str, str]:
    """
    Generate narrative architecture summaries.

    Args:
        report : ArchitectureReport from analyze()
        llm    : optional LangChain LLM instance. If None or if calls fail,
                 falls back to template-based summaries.

    Returns:
        Dict[section_name -> text]
    """
    report_text = _report_to_text(report)

    # Start with template summaries as baseline
    summaries = _template_summaries(report)

    if llm is None:
        return summaries

    # Attempt to enhance each section with LLM
    prompt_map = {
        "layer_summary":    LAYER_SUMMARY_PROMPT.format(report_text=report_text),
        "module_summary":   MODULE_SUMMARY_PROMPT.format(report_text=report_text),
        "spring_patterns":  SPRING_PATTERNS_PROMPT.format(report_text=report_text),
        "onboarding_intro": ONBOARDING_INTRO_PROMPT.format(report_text=report_text),
        "quick_start":      QUICK_START_PROMPT.format(report_text=report_text),
        "critique":         ARCHITECTURE_CRITIQUE_PROMPT.format(report_text=report_text),
    }

    for section, prompt in prompt_map.items():
        result = _llm_summary(llm, ARCHITECTURE_SYSTEM_PROMPT, prompt)
        if result:
            summaries[section] = result

    return summaries
