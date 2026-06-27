from __future__ import annotations
"""
RetroDecrypt LangGraph Agent tools.

Tool catalogue (Phases 1-8):
  search_repository        -- vector + BM25 hybrid semantic search over code
  analyze_dependencies     -- dependency graph queries
  analyze_architecture_tool -- layer/module/Spring pattern analysis
  explain_code             -- focused LLM explanation of a specific class/method
  get_documentation        -- retrieve sections from the generated onboarding doc
  review_code_quality      -- Phase 8: full static code review (all categories)
  analyze_solid_principles -- Phase 8: SOLID-only analysis
  detect_security_issues   -- Phase 8: security vulnerability scan
  analyze_technical_debt   -- Phase 8: tech debt + duplicate code scan
"""

import json
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_EMBEDDINGS  = None
_VECTORDB    = None
_RETRIEVER   = None
_METADATA    = None
_GRAPH       = None
_ARCH_REPORT = None
_REVIEW_ENGINE = None


def _get_embeddings():
    global _EMBEDDINGS
    if _EMBEDDINGS is None:
        from src.embeddings import load_embeddings
        _EMBEDDINGS = load_embeddings()
    return _EMBEDDINGS


def _get_vectordb():
    global _VECTORDB
    if _VECTORDB is None:
        from src.vector_store import load_vector_store
        _VECTORDB = load_vector_store(_get_embeddings())
    return _VECTORDB


def _get_retriever():
    global _RETRIEVER
    if _RETRIEVER is None:
        from src.retriever import build_retriever
        from src.chunker import build_documents
        try:
            docs = build_documents(_get_metadata())
        except Exception:
            docs = None
        _RETRIEVER = build_retriever(_get_vectordb(), docs)
    return _RETRIEVER


def _get_metadata():
    global _METADATA
    if _METADATA is None:
        from src.ingest import load_metadata
        _METADATA = load_metadata()
    return _METADATA


def _get_dep_graph():
    global _GRAPH
    if _GRAPH is None:
        from src.dependency import build_full_graph
        _GRAPH = build_full_graph(_get_metadata())
    return _GRAPH


def _get_arch_report():
    global _ARCH_REPORT
    if _ARCH_REPORT is None:
        from src.architecture import analyze_architecture
        _ARCH_REPORT = analyze_architecture(_get_metadata())
    return _ARCH_REPORT


# ---------------------------------------------------------------------------
# Tool 1: Repository Search
# ---------------------------------------------------------------------------

@tool
def search_repository(query: str) -> str:
    """
    Semantic and keyword search over the Java repository source code.

    Use this tool to find implementations, usages of annotations, design
    patterns, or any question that requires reading actual source code.

    Args:
        query: Natural language description of what to find in the code.
               Include class names, method names, or annotations when known.

    Returns:
        Relevant code snippets with file names and class context.
    """
    try:
        retriever = _get_retriever()
        docs = retriever.invoke(query)
        if not docs:
            return "No relevant code found for this query."
        parts = []
        for i, doc in enumerate(docs, 1):
            meta   = doc.metadata
            file_  = Path(meta.get('file', 'unknown')).name
            class_ = meta.get('class', '')
            method = meta.get('method', '')
            ctype  = meta.get('chunk_type', '')
            header = f'[{i}] {file_}'
            if class_:
                header += f' >> {class_}'
            if method:
                header += f'.{method}()'
            if ctype:
                header += f' [{ctype}]'
            parts.append(header + chr(10) + doc.page_content[:800])
        sep = chr(10)*2 + '---' + chr(10)*2
        return sep.join(parts)
    except Exception as exc:
        return f'Search error: {exc}'


# ---------------------------------------------------------------------------
# Tool 2: Dependency Analysis
# ---------------------------------------------------------------------------

@tool
def analyze_dependencies(
    query_type: str,
    class_name: str = '',
    source_class: str = '',
    target_class: str = '',
) -> str:
    """
    Query the Java dependency graph built from import and injection analysis.

    query_type options:
      who_depends_on    -- which classes depend on class_name
      get_dependencies  -- what does class_name depend on
      dependency_chain  -- shortest path from source_class to target_class
      cycles            -- detect circular dependencies
      most_depended_on  -- top 10 most-used classes
      orphans           -- classes with no connections
      stats             -- overall graph statistics
      by_type           -- list all classes of a role

    Args:
        query_type:   One of the options above.
        class_name:   Class name for who_depends_on/get_dependencies/by_type.
        source_class: Source for dependency_chain.
        target_class: Destination for dependency_chain.
    """
    try:
        G = _get_dep_graph()
        from src.dependency.queries import DependencyQueryEngine
        from src.dependency.analyzer import analyze
        engine = DependencyQueryEngine(G)

        if query_type == 'who_depends_on':
            if not class_name:
                return 'class_name is required'
            result = engine.who_depends_on(class_name)
            if not result:
                return f'No classes depend on {class_name}.'
            lines = [f'Classes that depend on {class_name}:']
            for r in result:
                lines.append(
                    f"  - {r['class']} ({r['class_type']}) "
                    f"[{r['relationship']}, {r['dep_type']}]"
                )
            return chr(10).join(lines)

        elif query_type == 'get_dependencies':
            if not class_name:
                return 'class_name is required'
            result = engine.get_dependencies(class_name)
            if not result:
                return f'{class_name} has no tracked dependencies.'
            lines = [f'Dependencies of {class_name}:']
            for r in result:
                lines.append(f"  - {r['class']} ({r['class_type']}) [{r['relationship']}]")
            return chr(10).join(lines)

        elif query_type == 'dependency_chain':
            if not source_class or not target_class:
                return 'Both source_class and target_class are required.'
            chain = engine.dependency_chain(source_class, target_class)
            if not chain:
                return f'No path from {source_class} to {target_class}.'
            return engine.format_chain(chain)

        elif query_type == 'cycles':
            report = analyze(G)
            if not report.circular_dependencies:
                return 'No circular dependencies detected.'
            lines = ['Circular dependencies found:']
            for c in report.circular_dependencies:
                lines.append(f'  - {c}')
            return chr(10).join(lines)

        elif query_type == 'most_depended_on':
            result = engine.most_depended_on(10)
            lines = ['Most depended-on classes:']
            for r in result:
                if r['dependents'] > 0:
                    lines.append(f"  - {r['class']} ({r['class_type']}): {r['dependents']} dependent(s)")
            return chr(10).join(lines)

        elif query_type == 'orphans':
            report = analyze(G)
            if not report.orphan_classes:
                return 'No orphan classes found.'
            lines = ['Orphan classes (no connections):'] + [f'  - {o}' for o in report.orphan_classes]
            return chr(10).join(lines)

        elif query_type == 'stats':
            return json.dumps(engine.graph_stats(), indent=2)

        elif query_type == 'by_type':
            if not class_name:
                return 'class_name (role name) is required for by_type.'
            result = engine.classes_by_type(class_name)
            if not result:
                return f'No classes found with role: {class_name}'
            lines = [f'{class_name.title()} classes:'] + [f'  - {c}' for c in result]
            return chr(10).join(lines)

        else:
            return (
                f'Unknown query_type: {query_type}. '
                'Choose from: who_depends_on, get_dependencies, dependency_chain, '
                'cycles, most_depended_on, orphans, stats, by_type'
            )
    except Exception as exc:
        return f'Dependency analysis error: {exc}'


# ---------------------------------------------------------------------------
# Tool 3: Architecture Analysis
# ---------------------------------------------------------------------------

@tool
def analyze_architecture_tool(
    aspect: str = 'summary',
    layer_name: str = '',
    module_name: str = '',
) -> str:
    """
    Query the architectural analysis of the Java repository.

    aspect options:
      summary       -- high-level architecture overview
      layers        -- all architectural layers with class counts
      modules       -- feature module boundaries
      spring_patterns -- Spring Boot patterns detected
      roles         -- class role distribution
      layer_detail  -- classes in a specific layer (requires layer_name)
      module_detail -- classes in a specific module (requires module_name)
      health        -- detection rate, unclassified classes

    Args:
        aspect:      Which aspect of the architecture to query.
        layer_name:  Layer name for layer_detail.
        module_name: Module name for module_detail.
    """
    try:
        report = _get_arch_report()

        if aspect == 'summary':
            return report.summary()

        elif aspect == 'layers':
            lines = ['Architectural Layers:']
            for layer in report.layers:
                if layer.class_count > 0:
                    pkgs = ', '.join(sorted(set(layer.packages))[:3])
                    lines.append(f'  {layer.name:<20} {layer.class_count:>3} class(es)  packages: {pkgs}')
            return chr(10).join(lines)

        elif aspect == 'modules':
            if not report.modules:
                return 'No feature modules detected (flat role-based package structure).'
            lines = ['Feature Modules:']
            for mod in report.modules:
                roles = ', '.join(sorted(mod.roles_present))
                fs = ' [full-stack]' if mod.is_full_stack else ''
                lines.append(f'  {mod.name:<20} {len(mod.classes):>3} classes  roles: {roles}{fs}')
            return chr(10).join(lines)

        elif aspect == 'spring_patterns':
            sp = report.spring_patterns
            lines = ['Spring Boot Patterns Detected:']
            for pat in sp.patterns_detected:
                lines.append(f'  + {pat}')
            lines += [
                '',
                f'  Entry Point  : {sp.entry_point_class or "not found"}',
                f'  Base Package : {sp.base_package or "unknown"}',
                f'  REST Controllers: {sp.rest_controller_count}',
                f'  JPA Entities    : {sp.jpa_entity_count}',
                f'  Spring Data Repos: {sp.spring_data_repo_count}',
                f'  Security : {"yes" if sp.has_security else "no"}',
                f'  Scheduling: {"yes" if sp.has_scheduling else "no"}',
                f'  Async     : {"yes" if sp.has_async else "no"}',
            ]
            return chr(10).join(lines)

        elif aspect == 'roles':
            from src.architecture.detector import ROLE_LABELS
            lines = ['Class Role Distribution:']
            for role, classes in sorted(report.roles_by_name.items(), key=lambda x: -len(x[1])):
                if not classes:
                    continue
                label = ROLE_LABELS.get(role, role)
                names = ', '.join(c.class_name for c in sorted(classes, key=lambda c: c.class_name)[:5])
                if len(classes) > 5:
                    names += f' +{len(classes)-5} more'
                lines.append(f'  {label:<25} ({len(classes):>3}): {names}')
            return chr(10).join(lines)

        elif aspect == 'layer_detail':
            if not layer_name:
                return 'layer_name is required for layer_detail.'
            layer = next((l for l in report.layers if l.name == layer_name), None)
            if not layer:
                avail = [l.name for l in report.layers if l.class_count > 0]
                return f'Layer not found. Available: {avail}'
            lines = [
                f'Layer: {layer.name} ({layer.class_count} classes)',
                f'Packages: {chr(44).join(sorted(set(layer.packages)))}',
                '',
                'Classes:',
            ]
            for cls in sorted(layer.classes, key=lambda c: c.class_name):
                anns = f' [@{chr(44).join(cls.annotations[:3])}]' if cls.annotations else ''
                lines.append(f'  {cls.class_name}{anns} in {cls.package}')
            return chr(10).join(lines)

        elif aspect == 'module_detail':
            if not module_name:
                return 'module_name is required for module_detail.'
            mod = next((m for m in report.modules if m.name == module_name), None)
            if not mod:
                avail = [m.name for m in report.modules]
                return f'Module not found. Available: {avail}'
            lines = [
                f'Module: {mod.name}',
                f'Root Package: {mod.root_package}',
                f'Full Stack: {"yes" if mod.is_full_stack else "no"}',
                f'Roles: {chr(44).join(sorted(mod.roles_present))}',
                '',
                'Classes:',
            ]
            for cls in sorted(mod.classes, key=lambda c: c.class_name):
                lines.append(f'  {cls.class_name} ({cls.role})')
            return chr(10).join(lines)

        elif aspect == 'health':
            stats = report.stats
            lines = [
                'Architecture Health:',
                f'  Total classes    : {stats.get("total_classes", 0)}',
                f'  Classified       : {stats.get("detected_classes", 0)}',
                f'  Unclassified     : {stats.get("unknown_classes", 0)}',
                f'  Detection rate   : {stats.get("detection_rate", 0)*100:.0f}%',
            ]
            unclassified = report.roles_by_name.get('unknown', [])
            if unclassified:
                lines.append('  Unclassified: ' + ', '.join(c.class_name for c in unclassified[:8]))
            return chr(10).join(lines)

        else:
            return (
                f'Unknown aspect: {aspect}. Choose from: '
                'summary, layers, modules, spring_patterns, roles, '
                'layer_detail, module_detail, health'
            )
    except Exception as exc:
        return f'Architecture analysis error: {exc}'


# ---------------------------------------------------------------------------
# Tool 4: Code Explanation
# ---------------------------------------------------------------------------

@tool
def explain_code(
    class_name: str,
    focus: str = '',
) -> str:
    """
    Retrieve source code for a specific Java class or method.

    Use when the user asks for a detailed explanation of what a specific
    class does, how a method works, or what a component is responsible for.

    Args:
        class_name: The exact Java class or interface name.
        focus:      Optional specific method or aspect to focus on.
    """
    try:
        retriever = _get_retriever()
        query = (class_name + ' ' + focus).strip()
        docs = retriever.invoke(query)
        relevant = [
            d for d in docs
            if class_name.lower() in d.metadata.get('class', '').lower()
            or class_name.lower() in Path(d.metadata.get('file', '')).name.lower()
        ]
        if not relevant:
            relevant = docs[:4]
        if not relevant:
            return f'No source code found for class: {class_name}'
        parts = []
        for doc in relevant:
            file_ = Path(doc.metadata.get('file', 'unknown')).name
            method = doc.metadata.get('method', '')
            header = f'FILE: {file_}'
            if method:
                header += f'  METHOD: {method}()'
            parts.append(header + chr(10)*2 + doc.page_content)
        return (chr(10)*2 + '===' + chr(10)*2).join(parts)
    except Exception as exc:
        return f'Code retrieval error: {exc}'


# ---------------------------------------------------------------------------
# Tool 5: Documentation
# ---------------------------------------------------------------------------

@tool
def get_documentation(section: str = 'overview') -> str:
    """
    Retrieve sections from the generated architecture onboarding documentation.

    section options:
      overview      -- project overview and key metrics
      quick_start   -- developer quick-start guide
      request_flow  -- how an HTTP request flows through the system
      layers        -- architectural layer breakdown
      modules       -- module boundary descriptions
      spring        -- Spring Boot patterns and technology stack
      diagrams      -- list of available Mermaid diagrams
      full          -- complete onboarding document

    Args:
        section: Which part of the documentation to retrieve.
    """
    try:
        from src.agent.config import AgentConfig
        cfg = AgentConfig()
        doc_path = cfg.onboarding_path
        if not doc_path.exists():
            return 'Onboarding documentation not found. Run build_architecture.py first.'
        full_doc = doc_path.read_text(encoding='utf-8')
        if section == 'full':
            return full_doc[:6000]
        SECTION_HEADERS = {
            'overview':     '1. Project Overview',
            'quick_start':  '10. Quick Start Guide',
            'request_flow': '8. Request Flow',
            'layers':       '4. Layered Architecture',
            'modules':      '7. Module Boundaries',
            'spring':       '6. Spring Boot Patterns',
            'diagrams':     '11. Architecture Diagrams',
        }
        header = SECTION_HEADERS.get(section.lower())
        if not header:
            return f'Unknown section: {section}. Choose from: ' + ', '.join(SECTION_HEADERS)
        lines = full_doc.split(chr(10))
        in_section = False
        section_lines = []
        section_level = 0
        for line in lines:
            if header in line and line.startswith('#'):
                in_section = True
                section_level = len(line) - len(line.lstrip('#'))
                section_lines.append(line)
                continue
            if in_section:
                if line.startswith('#'):
                    cur_level = len(line) - len(line.lstrip('#'))
                    if cur_level <= section_level:
                        break
                section_lines.append(line)
        if not section_lines:
            return f'Section not found in documentation.'
        return chr(10).join(section_lines).strip()[:4000]
    except Exception as exc:
        return f'Documentation retrieval error: {exc}'


# ---------------------------------------------------------------------------
# Phase 8 lazy singleton helper
# ---------------------------------------------------------------------------

def _get_review_engine():
    global _REVIEW_ENGINE
    if _REVIEW_ENGINE is None:
        from src.code_review import CodeReviewEngine
        from src.agent.config import AgentConfig
        cfg = AgentConfig()
        _REVIEW_ENGINE = CodeReviewEngine(repo_root=str(cfg.project_root))
    return _REVIEW_ENGINE


# ---------------------------------------------------------------------------
# Tool 6: Full Code Review (Phase 8)
# ---------------------------------------------------------------------------

@tool
def review_code_quality(
    target_class: str = '',
    categories: str = 'all',
) -> str:
    """
    Run a comprehensive static code review over the Java repository.

    Analyses SOLID principles, design patterns, security vulnerabilities,
    performance issues, maintainability, duplicate code, and technical debt.

    Args:
        target_class: Optional Java class name to focus the review on a single class.
                      Leave empty to review the full repository.
        categories:   Comma-separated list of categories to run, or 'all'.
                      Options: solid, security, performance, maintainability,
                               duplicates, tech_debt, patterns.

    Returns:
        Structured code review report text with findings, severity, and recommendations.
    """
    try:
        metadata = _get_metadata()
        engine   = _get_review_engine()

        # Parse categories
        enabled = None
        if categories and categories.lower() != 'all':
            enabled = [c.strip() for c in categories.split(',') if c.strip()]

        from src.code_review import CodeReviewEngine
        from src.agent.config import AgentConfig
        cfg = AgentConfig()
        review_engine = CodeReviewEngine(
            repo_root=str(cfg.project_root),
            enabled_analyzers=enabled,
        )

        target_list = [target_class] if target_class else None
        report = review_engine.run(metadata, target_classes=target_list)

        # Return a concise but complete text summary
        lines = [
            f'Code Review Results',
            f'Files reviewed : {report.reviewed_files}',
            f'Total classes  : {report.total_classes}',
            f'Total findings : {report.total_findings}',
            f'Quality score  : {report.quality_score:.1f}/100 (Grade: {report.grade})',
            '',
            report.summary,
            '',
        ]

        # Top issues
        if report.top_issues:
            lines += ['TOP ISSUES:']
            for issue in report.top_issues:
                lines.append(f'  {issue}')
            lines.append('')

        # Category breakdown
        lines += ['FINDINGS BY CATEGORY:']
        for cs in report.category_summaries:
            if cs.total > 0:
                lines.append(
                    f'  {cs.category.value:<22} {cs.total:>3} '
                    f'(C:{cs.critical} H:{cs.high} M:{cs.medium} L:{cs.low})'
                )
        lines.append('')

        # CRITICAL and HIGH findings in detail
        critical_high = [
            f for f in report.findings
            if f.severity.value in ('critical', 'high')
        ][:15]
        if critical_high:
            lines += ['CRITICAL/HIGH FINDINGS (detail):']
            for f in critical_high:
                lines += [
                    f'  [{f.severity.value.upper()}] [{f.rule_id}] {f.title}',
                    f'    Classes: {", ".join(f.affected_classes[:3])}',
                    f'    Desc: {f.description[:200]}',
                    f'    Fix: {f.recommendation[:200]}',
                    '',
                ]

        return chr(10).join(lines)
    except Exception as exc:
        return f'Code review error: {exc}'


# ---------------------------------------------------------------------------
# Tool 7: SOLID Principles Analysis (Phase 8)
# ---------------------------------------------------------------------------

@tool
def analyze_solid_principles(
    target_class: str = '',
) -> str:
    """
    Analyse SOLID principles adherence for Java classes in the repository.

    Checks Single Responsibility, Open/Closed, Liskov Substitution,
    Interface Segregation, and Dependency Inversion principles.

    Args:
        target_class: Optional class name to focus on. Leave empty for full analysis.

    Returns:
        SOLID violation findings with severity and refactoring recommendations.
    """
    try:
        metadata = _get_metadata()
        from src.code_review import CodeReviewEngine
        from src.agent.config import AgentConfig
        cfg = AgentConfig()
        engine = CodeReviewEngine(
            repo_root=str(cfg.project_root),
            enabled_analyzers=['solid'],
        )
        target_list = [target_class] if target_class else None
        report = engine.run(metadata, target_classes=target_list)

        if not report.findings:
            return 'No SOLID violations detected.'

        lines = [f'SOLID Principles Analysis ({report.total_findings} findings):']
        for f in sorted(report.findings, key=lambda x: list(x.severity.__class__).index(x.severity)):
            lines += [
                f'  [{f.severity.value.upper()}] [{f.rule_id}] {f.title}',
                f'    Classes: {", ".join(f.affected_classes[:3])}',
                f'    Issue: {f.description[:200]}',
                f'    Fix: {f.recommendation[:200]}',
                '',
            ]
        return chr(10).join(lines)
    except Exception as exc:
        return f'SOLID analysis error: {exc}'


# ---------------------------------------------------------------------------
# Tool 8: Security Analysis (Phase 8)
# ---------------------------------------------------------------------------

@tool
def detect_security_issues(
    target_class: str = '',
) -> str:
    """
    Scan the Java repository for security vulnerabilities (OWASP Top 10 aligned).

    Detects SQL injection, hardcoded credentials, weak cryptography, missing
    input validation, insecure deserialization, path traversal, and more.

    Args:
        target_class: Optional class name to focus on. Leave empty for full scan.

    Returns:
        Security findings with severity (CRITICAL/HIGH/MEDIUM) and remediation steps.
    """
    try:
        metadata = _get_metadata()
        from src.code_review import CodeReviewEngine
        from src.agent.config import AgentConfig
        cfg = AgentConfig()
        engine = CodeReviewEngine(
            repo_root=str(cfg.project_root),
            enabled_analyzers=['security'],
        )
        target_list = [target_class] if target_class else None
        report = engine.run(metadata, target_classes=target_list)

        if not report.findings:
            return 'No security issues detected.'

        lines = [f'Security Analysis ({report.total_findings} finding(s)):']
        for f in sorted(report.findings, key=lambda x: list(x.severity.__class__).index(x.severity)):
            lines += [
                f'  [{f.severity.value.upper()}] [{f.rule_id}] {f.title}',
                f'    Classes: {", ".join(f.affected_classes[:3])}',
                f'    Risk: {f.description[:200]}',
                f'    Remediation: {f.recommendation[:200]}',
                '',
            ]
        return chr(10).join(lines)
    except Exception as exc:
        return f'Security scan error: {exc}'


# ---------------------------------------------------------------------------
# Tool 9: Technical Debt Analysis (Phase 8)
# ---------------------------------------------------------------------------

@tool
def analyze_technical_debt(
    target_class: str = '',
) -> str:
    """
    Detect technical debt and duplicate code in the Java repository.

    Identifies TODO/FIXME comments, missing tests, hardcoded values,
    deprecated API usage, structural code clones, and duplicate method signatures.

    Args:
        target_class: Optional class name to focus on. Leave empty for full scan.

    Returns:
        Technical debt findings with priority and recommended actions.
    """
    try:
        metadata = _get_metadata()
        from src.code_review import CodeReviewEngine
        from src.agent.config import AgentConfig
        cfg = AgentConfig()
        engine = CodeReviewEngine(
            repo_root=str(cfg.project_root),
            enabled_analyzers=['tech_debt', 'duplicates'],
        )
        target_list = [target_class] if target_class else None
        report = engine.run(metadata, target_classes=target_list)

        if not report.findings:
            return 'No technical debt detected.'

        lines = [f'Technical Debt Analysis ({report.total_findings} finding(s)):']
        for f in sorted(report.findings, key=lambda x: list(x.severity.__class__).index(x.severity)):
            lines += [
                f'  [{f.severity.value.upper()}] [{f.rule_id}] {f.title}',
                f'    Classes: {", ".join(f.affected_classes[:3])}',
                f'    Debt: {f.description[:200]}',
                f'    Action: {f.recommendation[:200]}',
                '',
            ]
        return chr(10).join(lines)
    except Exception as exc:
        return f'Tech debt analysis error: {exc}'


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

ALL_TOOLS = [
    search_repository,
    analyze_dependencies,
    analyze_architecture_tool,
    explain_code,
    get_documentation,
    # Phase 8
    review_code_quality,
    analyze_solid_principles,
    detect_security_issues,
    analyze_technical_debt,
]