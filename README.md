# Java Repository Intelligence Platform

> Enterprise-grade AI-powered analysis for Java / Spring Boot codebases.

---

## Quick Start (3 steps)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create a .env file with your LLM API key  (see §4 below)

# 3. Run the platform
python run.py
```

`python run.py` is the single entry point — it handles ingestion, user
profiling, `.docx` documentation generation, and interactive Q&A chat.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Step-by-Step Setup](#4-step-by-step-setup)
5. [Running the Platform — python run.py](#5-running-the-platform)
6. [User Profiling and Personalised Documentation](#6-user-profiling-and-personalised-documentation)
7. [Optional: Individual Phase Scripts](#7-optional-individual-phase-scripts)
8. [REST API (Phase 9)](#8-rest-api-phase-9)
9. [Testing](#9-testing)
10. [Project Structure](#10-project-structure)
11. [Phase Reference](#11-phase-reference)
12. [Configuration Reference](#12-configuration-reference)

---

## 1. Project Overview

The Java Repository Intelligence Platform provides automated, AI-powered understanding of large Java and Spring Boot codebases. It combines static analysis, semantic search, dependency graph reasoning, architecture pattern detection, and agentic LLM workflows to give developers and architects deep insight into any Java repository without manual code exploration.

### Target Capabilities

| Capability                   | Phase | Status      |
|------------------------------|-------|-------------|
| Repository ingestion         | 1     | ✅ Complete  |
| Semantic code search         | 2     | ✅ Complete  |
| Conversational RAG           | 3     | ✅ Complete  |
| Dependency intelligence      | 4     | ✅ Complete  |
| Architecture intelligence    | 5     | ✅ Complete  |
| Agentic workflows            | 6     | ✅ Complete  |
| Multi-agent orchestration    | 7     | ✅ Complete  |
| Code review intelligence     | 8     | ✅ Complete  |
| Enterprise platform (FastAPI)| 9     | ✅ Complete  |

---

## 2. Architecture

```
                         ┌─────────────────────────────────────────┐
                         │        User / Agent Query Interface      │
                         └──────────────────┬──────────────────────┘
                                            │
                         ┌──────────────────▼──────────────────────┐
                         │         Multi-Agent Coordinator          │
                         │  (LangGraph StateGraph + RoutingDecision)│
                         └───┬──────┬──────┬──────┬──────┬─────────┘
                             │      │      │      │      │
               ┌─────────────┘  ┌───┘  ┌──┘  ┌──┘   ┌──┘
               ▼                ▼      ▼     ▼      ▼
        ┌─────────┐  ┌──────────┐  ┌──────┐  ┌─────┐  ┌────────────┐
        │  Search  │  │  Arch.   │  │  Dep │  │Docs │  │   Review   │
        │  Agent   │  │  Agent   │  │ Agent│  │Agent│  │   Agent    │
        └────┬─────┘  └────┬─────┘  └──┬───┘  └──┬──┘  └─────┬──────┘
             │             │           │         │            │
    ┌────────▼─────────────▼───────────▼─────────▼────────────▼────────┐
    │                     Shared Tool Layer                              │
    │  search_repository  |  analyze_architecture_tool                  │
    │  analyze_dependencies | explain_code | get_documentation          │
    │  review_code_quality | analyze_solid_principles                   │
    │  detect_security_issues | analyze_technical_debt  (Phase 8)       │
    └────────────┬─────────────────────────────────┬────────────────────┘
                 │                                 │
    ┌────────────▼──────────┐       ┌──────────────▼──────────────┐
    │   ChromaDB VectorDB   │       │    Static Analysis Engine    │
    │  + BGE Embeddings     │       │    (Phase 8: Code Review)    │
    │  + BM25 Hybrid Search │       │                              │
    └────────────┬──────────┘       └──────────────┬──────────────┘
                 │                                 │
    ┌────────────▼──────────┐       ┌──────────────▼──────────────┐
    │  Repository Metadata  │       │    NetworkX Dependency       │
    │  (repository_metadata │       │    Graph + Architecture      │
    │   .json)              │       │    Report                    │
    └───────────────────────┘       └─────────────────────────────┘
```

---

## 3. Technology Stack

| Component           | Technology                                   |
|---------------------|----------------------------------------------|
| LLM                 | Gemini / OpenAI GPT / Anthropic Claude — switchable via `LLM_PROVIDER` in `.env` |
| Agent Framework     | LangGraph (StateGraph, Send API)              |
| LLM Orchestration   | LangChain (tools, messages, chains)           |
| Vector Store        | ChromaDB                                      |
| Embeddings          | BGE (via `langchain-huggingface`)             |
| Hybrid Search       | BM25 + semantic (via `rank-bm25`)             |
| Dependency Graph    | NetworkX                                      |
| Data Models         | Pydantic v2                                   |
| Java Parsing        | tree-sitter + tree-sitter-java                |
| Testing             | pytest                                        |
| Runtime             | Python 3.12+                                  |
| REST API            | FastAPI (Phase 9)                             |
| Database            | PostgreSQL (prod) / SQLite (dev/test)         |

---

## 4. Project Structure

```
java-intelligence/
├── src/
│   ├── __init__.py
│   ├── chat.py                    # Conversational interface
│   ├── chunker.py                 # Metadata-aware Java code chunker
│   ├── embeddings.py              # BGE embedding loader
│   ├── ingest.py                  # Repository metadata loader
│   ├── llm.py                     # Multi-provider LLM factory (Gemini / OpenAI / Anthropic)
│   ├── models.py                  # JavaFileMetadata Pydantic model
│   ├── parser.py                  # Java AST parser
│   ├── prompts.py                 # RAG system prompts
│   ├── rag_chain.py               # LangChain RAG chain
│   ├── retriever.py               # Hybrid retriever (BM25 + semantic)
│   ├── scanner.py                 # Repository scanner
│   ├── vector_store.py            # ChromaDB vector store
│   │
│   ├── agent/                     # Phase 6 + 7: LangGraph agents
│   │   ├── __init__.py
│   │   ├── config.py              # AgentConfig dataclass
│   │   ├── graph.py               # Single-agent LangGraph graph
│   │   ├── memory.py              # Conversation memory
│   │   ├── multi_graph.py         # Multi-agent LangGraph graph
│   │   ├── state.py               # MultiAgentState TypedDict
│   │   ├── tools.py               # All agent tools (Phases 1-8)
│   │   └── agents/
│   │       ├── __init__.py
│   │       ├── coordinator.py     # Coordinator + Synthesizer nodes
│   │       └── specialists.py     # Specialist agent factories
│   │
│   ├── architecture/              # Phase 5: Architecture intelligence
│   │   ├── __init__.py
│   │   ├── analyzer.py            # ArchitectureReport builder
│   │   ├── c4.py                  # C4 model generation
│   │   ├── detector.py            # Class role detector
│   │   ├── diagram.py             # Mermaid diagram generator
│   │   ├── onboarding.py          # Onboarding doc generator
│   │   ├── prompts.py             # Architecture LLM prompts
│   │   └── summarizer.py         # Architecture summary
│   │
│   ├── dependency/                # Phase 4: Dependency intelligence
│   │   ├── __init__.py
│   │   ├── analyzer.py            # Dependency analysis + metrics
│   │   ├── exporter.py            # Graph export (JSON, DOT)
│   │   ├── extractor.py           # Import + injection extractor
│   │   ├── graph.py               # NetworkX graph builder
│   │   └── queries.py             # DependencyQueryEngine
│   │
│   └── code_review/               # Phase 8: Code Review Intelligence
│       ├── __init__.py
│       ├── models.py              # ReviewFinding, CodeReviewReport, Severity
│       ├── engine.py              # CodeReviewEngine orchestrator
│       ├── prompts.py             # LLM deep-review prompts + parser
│       └── analyzers/
│           ├── __init__.py
│           ├── solid.py           # SOLID principles (S001-D002)
│           ├── security.py        # Security vulnerabilities (SEC-001 to SEC-010)
│           ├── performance.py     # Performance issues (PERF-001 to PERF-008)
│           ├── maintainability.py # Maintainability (MAINT-001 to MAINT-010)
│           ├── duplicates.py      # Duplicate code (DUP-001 to DUP-003)
│           ├── tech_debt.py       # Technical debt (DEBT-001 to DEBT-009)
│           └── patterns.py        # Design patterns + anti-patterns (PAT/ANTI)
│
├── data/                          # Generated analysis artefacts
│   ├── repository_metadata.json
│   ├── dependency_graph.json
│   ├── dependency_adjacency.json
│   ├── architecture_report.json
│   ├── architecture_c4.txt
│   ├── architecture_diagrams.md
│   └── onboarding.md
│
├── src/platform/                  # Phase 9: Enterprise Platform
│   ├── __init__.py
│   ├── config.py                  # PlatformSettings (pydantic-settings, PLATFORM_ prefix)
│   ├── database.py                # SQLAlchemy engine + session + Base
│   ├── main.py                    # FastAPI app factory, lifespan, bootstrap admin
│   ├── auth/                      # JWT (python-jose), bcrypt, RBAC dependencies
│   │   ├── __init__.py
│   │   ├── hashing.py             # bcrypt password hash / verify
│   │   ├── jwt.py                 # create/decode access + refresh tokens
│   │   └── dependencies.py        # FastAPI deps: get_current_user, require_admin …
│   ├── models/                    # SQLAlchemy 2.0 ORM models
│   │   ├── __init__.py
│   │   ├── user.py                # User, UserRole
│   │   ├── repository.py          # Repository, RepositoryAccess, AnalysisJob
│   │   └── audit.py               # AuditLog
│   ├── schemas/                   # Pydantic v2 request/response schemas
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── user.py
│   │   ├── repository.py
│   │   └── audit.py
│   ├── services/                  # Business logic
│   │   ├── __init__.py
│   │   ├── audit_service.py
│   │   ├── user_service.py
│   │   └── repository_service.py
│   ├── jobs/                      # Background analysis pipeline
│   │   ├── __init__.py
│   │   └── pipeline.py            # Phase 1-8 orchestration per job type
│   └── api/v1/                    # FastAPI routers
│       ├── __init__.py
│       ├── auth.py                # POST /register /login /refresh /logout
│       ├── users.py               # User CRUD + role management
│       ├── repositories.py        # Repository CRUD + scan trigger + reports
│       ├── chat.py                # Per-repo RAG / multi-agent Q&A
│       ├── review.py              # On-demand code review
│       └── audit.py               # Audit log (admin only)
│
├── data/
│   ├── repository_metadata.json   # Global (pre-Phase 9) metadata
│   ├── dependency_graph.json
│   ├── dependency_adjacency.json
│   ├── architecture_report.json
│   ├── architecture_c4.txt
│   ├── architecture_diagrams.md
│   ├── onboarding.md
│   └── repositories/              # Per-repo data (Phase 9)
│       └── {repo_id}/
│           ├── metadata.json
│           ├── dependency_graph.json
│           ├── architecture_report.json
│           ├── onboarding.md
│           ├── code_review_report.json
│           └── vectordb/
│
├── vectordb/                      # ChromaDB persistent store (global / pre-Phase 9)
│
├── sample_spring_repo/            # Sample Spring Boot repository for testing
│
├── build_vector_db.py             # Build/refresh ChromaDB index
├── build_dependency_graph.py      # Build dependency graph
├── build_architecture.py          # Build architecture report
├── run_agent.py                   # Single-agent REPL
├── run_multi_agent.py             # Multi-agent REPL
├── test_code_review.py            # Phase 8 test suite (45 tests)
├── test_platform.py               # Phase 9 test suite (61 tests)
├── requirements.txt
└── README.md                      # This file
```

---

## 5. Phase 1 — Repository Ingestion

**Module:** `src/scanner.py`, `src/parser.py`, `src/models.py`, `src/ingest.py`

Scans a Java repository and extracts structured metadata from every `.java` file.

### Extracted Metadata (`JavaFileMetadata`)

| Field          | Type           | Description                          |
|----------------|----------------|--------------------------------------|
| `file_path`    | `str`          | Absolute or relative path            |
| `package`      | `Optional[str]`| Java package declaration             |
| `imports`      | `List[str]`    | All import statements                |
| `annotations`  | `List[str]`    | Class-level annotations              |
| `classes`      | `List[str]`    | Class names declared in the file     |
| `interfaces`   | `List[str]`    | Interface names                      |
| `enums`        | `List[str]`    | Enum names                           |
| `methods`      | `List[str]`    | Public/protected method names        |
| `lines_of_code`| `int`          | Non-blank source lines               |
| `content_hash` | `str`          | SHA-256 hash for change detection    |

### Output

`data/repository_metadata.json` — repository knowledge model used by all downstream phases.

---

## 6. Phase 2 — Semantic Retrieval

**Module:** `src/chunker.py`, `src/embeddings.py`, `src/vector_store.py`, `src/retriever.py`

### How It Works

1. **Chunking** — Java files are split into class-level and method-level chunks, each carrying rich metadata.
2. **Embeddings** — BAAI/bge-large-en-v1.5 model generates dense vectors for each chunk.
3. **Indexing** — Chunks are stored in ChromaDB with metadata filtering support.
4. **Retrieval** — Hybrid BM25 + semantic search with configurable `k` and `fetch_k`.

### Retrieval Capabilities

- Similarity search over the full codebase
- Metadata-filtered search (by class, annotation, package, chunk type)
- Repository-wide search with contextual ranking

---

## 7. Phase 3 — Conversational RAG

**Module:** `src/rag_chain.py`, `src/prompts.py`, `src/chat.py`, `src/llm.py`

### Capabilities

- Natural language Q&A over the repository using any configured LLM provider
- Source citations (file name + class name for every answer)
- Context grounding (answers are always rooted in retrieved code)
- Multi-turn conversation with sliding window memory

### Example Questions

- "Explain how CustomerService processes an order"
- "What does the EmailService do?"
- "Show me all REST endpoints"
- "How is authentication handled?"

---

## 8. Phase 4 — Dependency Intelligence

**Module:** `src/dependency/`

### Detection Scope

- Java `import` statements
- Spring `@Autowired` / constructor injection relationships
- Field declaration types

### Analysis Capabilities

| Query Type        | Description                                            |
|-------------------|--------------------------------------------------------|
| `who_depends_on`  | Reverse dependencies — who uses this class             |
| `get_dependencies`| Forward dependencies — what this class depends on      |
| `dependency_chain`| Shortest path between two classes                      |
| `cycles`          | Circular dependency detection (via `nx.simple_cycles`) |
| `most_depended_on`| Top-N most-imported classes                            |
| `orphans`         | Classes with no dependency connections                 |
| `stats`           | Graph statistics (nodes, edges, density)               |

### Metrics

- **Afferent coupling (Ca)** — how many classes depend on this class
- **Efferent coupling (Ce)** — how many classes this class depends on
- **Instability (I)** — `Ce / (Ca + Ce)`, 0 = stable, 1 = instable

---

## 9. Phase 5 — Architecture Intelligence

**Module:** `src/architecture/`

### Detection Capabilities

Detects Spring Boot class roles from annotations, naming, and package structure:

| Role            | Annotations / Naming                              |
|-----------------|---------------------------------------------------|
| `controller`    | `@RestController`, `@Controller`, `*Controller`   |
| `service`       | `@Service`, `*Service`, `*Facade`                 |
| `repository`    | `@Repository`, `*Repository`, `*Dao`              |
| `entity`        | `@Entity`, `@Document`, `*Entity`                 |
| `configuration` | `@Configuration`, `*Config`, `*Properties`        |
| `dto`           | `*DTO`, `*Request`, `*Response`, `*Payload`       |
| `utility`       | `*Util`, `*Utils`, `*Helper`, `*Constants`        |
| `component`     | `@Component`, `@Aspect`, `@Scheduled`             |

### Outputs

- **Architecture report** — layered summary, module map, Spring pattern inventory
- **Mermaid diagrams** — dependency graph, layer diagram, module diagram
- **C4 model** — Context, Container, Component descriptions
- **Onboarding documentation** — developer-ready `onboarding.md`

---

## 10. Phase 6 — LangGraph Agent

**Module:** `src/agent/graph.py`, `src/agent/tools.py`

Single-agent LangGraph graph with full tool access and conversation memory.

### Tools (Phases 1-8)

| Tool                        | Phase | Purpose                                  |
|-----------------------------|-------|------------------------------------------|
| `search_repository`         | 2     | Hybrid semantic code search              |
| `analyze_dependencies`      | 4     | Dependency graph queries                 |
| `analyze_architecture_tool` | 5     | Architecture layer/module analysis       |
| `explain_code`              | 2     | Class/method explanation                 |
| `get_documentation`         | 5     | Onboarding doc retrieval                 |
| `review_code_quality`       | 8     | Full code review (all categories)        |
| `analyze_solid_principles`  | 8     | SOLID analysis                           |
| `detect_security_issues`    | 8     | Security vulnerability scan              |
| `analyze_technical_debt`    | 8     | Tech debt + duplicate detection          |

---

## 11. Phase 7 — Multi-Agent System

**Module:** `src/agent/multi_graph.py`, `src/agent/agents/`

### Architecture

```
START → [Coordinator] → (parallel dispatch via LangGraph Send API)
          ↓        ↓        ↓         ↓         ↓
       [Search] [Arch.] [Depend.] [Docs]  [Review (Phase 8)]
          ↓        ↓        ↓         ↓         ↓
        agent_results (merged via _merge_dicts reducer)
                      ↓
              [Coordinator] (re-evaluates: more agents or FINISH?)
                      ↓
              [Synthesizer] → final_answer → END
```

### Agents

| Agent          | System Prompt Focus                                        | Phase 8 Tools Used      |
|----------------|-------------------------------------------------------------|-------------------------|
| `search`       | Semantic code search                                        | —                       |
| `architecture` | Layer/module/Spring Boot patterns                           | —                       |
| `dependency`   | Dependency graph queries, cycle detection                   | —                       |
| `docs`         | Onboarding documentation retrieval                          | —                       |
| `review`       | Code review intelligence (SOLID, security, perf, debt)      | All Phase 8 tools       |

### State

`MultiAgentState` carries: `messages`, `query`, `active_agents`, `agent_results`, `next_agents`, `iterations`, `final_answer`, `task_context`.

---

## 12. Phase 8 — Code Review Intelligence

**Module:** `src/code_review/`

Phase 8 delivers production-grade static code analysis with 7 analyzer categories, a scoring engine, and optional LLM deep-review enrichment.

### Architecture

```
CodeReviewEngine
    ├── analyze_solid()           → SOLID principles (9 rules)
    ├── analyze_security()        → Security vulnerabilities (10 rules)
    ├── analyze_performance()     → Performance issues (8 rules)
    ├── analyze_maintainability() → Maintainability (10 rules)
    ├── analyze_duplicates()      → Duplicate code (3 rules)
    ├── analyze_tech_debt()       → Technical debt (9 rules)
    ├── analyze_patterns()        → Design patterns + anti-patterns (12 rules)
    └── _llm_review()             → Optional LLM deep-review pass
```

### Rule Catalogue

#### SOLID Principles

| Rule ID    | Principle | Description                                               | Severity |
|------------|-----------|-----------------------------------------------------------|----------|
| SOLID-S001 | SRP       | Class has too many methods (> 15)                         | MEDIUM   |
| SOLID-S002 | SRP       | Class is too large (> 300 LOC)                            | LOW–MED  |
| SOLID-S003 | SRP       | Class imports from too many unrelated domains              | LOW      |
| SOLID-O001 | OCP       | Multiple `instanceof` type checks (use polymorphism)       | MEDIUM   |
| SOLID-O002 | OCP       | Long `else-if` chain (≥ 4 branches)                       | LOW      |
| SOLID-L001 | LSP       | Throws `UnsupportedOperationException`                    | HIGH     |
| SOLID-I001 | ISP       | Fat interface with > 10 method declarations               | MEDIUM   |
| SOLID-D001 | DIP       | `@Autowired` field injection (prefer constructor)          | MEDIUM   |
| SOLID-D002 | DIP       | Direct `new ConcreteClass()` instantiation                 | LOW      |

#### Security (OWASP-aligned)

| Rule ID | Description                                              | Severity |
|---------|----------------------------------------------------------|----------|
| SEC-001 | SQL injection via string concatenation in queries         | CRITICAL |
| SEC-002 | Hardcoded credentials / secrets in source code            | CRITICAL |
| SEC-003 | Missing `@Valid` on `@RequestBody` parameters             | MEDIUM   |
| SEC-004 | Sensitive data logged (password, token, credential)       | HIGH     |
| SEC-005 | Weak cryptographic algorithm (MD5, SHA-1, DES)           | HIGH     |
| SEC-006 | Insecure `java.util.Random` in security context           | MEDIUM   |
| SEC-007 | Unsafe `ObjectInputStream` deserialization                | HIGH     |
| SEC-008 | Path traversal risk (user input in file paths)            | HIGH     |
| SEC-009 | No method-level security annotation on REST controller    | INFO     |
| SEC-010 | Spring Security CSRF protection explicitly disabled       | HIGH     |

#### Performance

| Rule ID   | Description                                                | Severity |
|-----------|------------------------------------------------------------|----------|
| PERF-001  | N+1 query: repository call inside a loop                   | HIGH     |
| PERF-002  | Missing `@Transactional(readOnly=true)` on read methods    | LOW      |
| PERF-003  | Unbounded `findAll()` without pagination                   | MEDIUM   |
| PERF-004  | `FetchType.EAGER` on `@OneToMany` / `@ManyToMany`          | MEDIUM   |
| PERF-005  | String concatenation with `+=` inside a loop               | LOW      |
| PERF-006  | Expensive methods missing `@Cacheable`                     | INFO     |
| PERF-007  | Coarse-grained `public synchronized` method                | MEDIUM   |
| PERF-008  | Async-named methods missing `@Async`                       | LOW      |

#### Maintainability

| Rule ID    | Description                                              | Severity |
|------------|----------------------------------------------------------|----------|
| MAINT-001  | Long methods (avg > 40 LOC per method)                   | LOW      |
| MAINT-002  | Deep nesting (≥ 5 levels of indentation)                 | MEDIUM   |
| MAINT-003  | Magic numbers (≥ 4 distinct unlabelled literals)         | LOW      |
| MAINT-003b | Magic strings (≥ 3 inline string literals)               | LOW      |
| MAINT-004  | Empty catch block (swallowed exception)                  | HIGH     |
| MAINT-006  | Single-character variable names (≥ 3 occurrences)        | LOW      |
| MAINT-007  | Long parameter list (> 5 parameters)                     | MEDIUM   |
| MAINT-009  | Low comment coverage (< 5% of LOC)                       | INFO     |
| MAINT-010  | Public mutable fields (break encapsulation)              | MEDIUM   |

#### Duplicate Code

| Rule ID | Description                                                 | Severity |
|---------|-------------------------------------------------------------|----------|
| DUP-001 | Identical method signature in 3+ classes                    | LOW      |
| DUP-002 | Structurally similar classes (Jaccard similarity ≥ 70%)     | MEDIUM   |
| DUP-003 | Near-identical import sets between classes (≥ 85% overlap)  | INFO     |

#### Technical Debt

| Rule ID  | Description                                               | Severity |
|----------|-----------------------------------------------------------|----------|
| DEBT-001 | TODO/FIXME/HACK/XXX comment annotations                   | LOW–MED  |
| DEBT-002 | `@Deprecated` annotation usage                            | MEDIUM   |
| DEBT-003 | Missing Javadoc on public API methods                     | LOW      |
| DEBT-005 | Hardcoded URLs, IPs, or port numbers                      | MEDIUM   |
| DEBT-006 | Deprecated Spring MVC patterns (removed in Spring 5)      | HIGH     |
| DEBT-007 | No test class found for a service/controller              | MEDIUM   |
| DEBT-009 | `System.exit()` in non-main class                         | HIGH     |

#### Design Patterns & Anti-patterns

| Rule ID   | Type         | Description                                             | Severity |
|-----------|--------------|---------------------------------------------------------|----------|
| PAT-001   | Pattern      | Singleton pattern detected (redundant in Spring beans)  | INFO     |
| PAT-002   | Pattern      | Factory Method pattern                                  | INFO     |
| PAT-003   | Pattern      | Builder pattern                                         | INFO     |
| PAT-004   | Pattern      | Observer / Event-driven pattern                         | INFO     |
| PAT-005   | Pattern      | Strategy pattern (interface with 3+ implementations)   | INFO     |
| ANTI-001  | Anti-pattern | God Class (> 500 LOC or > 20 methods)                  | MED–HIGH |
| ANTI-002  | Anti-pattern | Service Locator (`applicationContext.getBean()`)        | HIGH     |
| ANTI-003  | Anti-pattern | Anemic Domain Model (entity with no domain methods)     | LOW      |
| ANTI-005  | Anti-pattern | Primitive Obsession (≥ 4 primitive params in a method)  | LOW      |
| ANTI-006  | Anti-pattern | Complex inheritance (multiple extends in one file)      | LOW      |

### Quality Scoring

The engine computes a **0-100 quality score** using a weighted penalty model:

```
penalty = Σ (finding_count × severity_weight)
where:  CRITICAL=10, HIGH=5, MEDIUM=2, LOW=1, INFO=0

class_scale = total_classes / 10

score = max(0, 100 - penalty / class_scale)
```

| Grade | Score Range |
|-------|-------------|
| A     | ≥ 90        |
| B     | ≥ 75        |
| C     | ≥ 60        |
| D     | ≥ 45        |
| F     | < 45        |

### Agent Integration

Phase 8 adds 4 new tools to the agent tool registry:

```python
review_code_quality(target_class="", categories="all")
analyze_solid_principles(target_class="")
detect_security_issues(target_class="")
analyze_technical_debt(target_class="")
```

The `review` specialist agent is upgraded to use all Phase 8 tools, enabling the multi-agent system to answer queries such as:
- "Are there any security vulnerabilities in the codebase?"
- "Does CustomerService follow SOLID principles?"
- "What is the technical debt level?"
- "Find duplicate code across services"
- "Review OrderController for production readiness"

### Programmatic Usage

```python
from src.code_review import CodeReviewEngine
from src.ingest import load_metadata

# Full repository review
engine = CodeReviewEngine(repo_root="/path/to/repo")
report = engine.run(load_metadata())

print(report.quality_score)        # e.g. 72.5
print(report.grade)                # e.g. "C"
print(report.to_text_report())     # full human-readable report

# Focused class review
report = engine.run_for_class("OrderService", load_metadata())

# Selective analyser categories
engine = CodeReviewEngine(
    repo_root="/path/to/repo",
    enabled_analyzers=["security", "solid"],
)
report = engine.run(load_metadata())

# Export JSON
engine.save_report(report, "data/code_review_report.json")
```

---

## 13. Phase 9 — Enterprise Platform

### Planned API Surface

```
POST   /api/v1/repositories            Register a new repository
GET    /api/v1/repositories            List repositories
POST   /api/v1/repositories/{id}/scan  Trigger full analysis
GET    /api/v1/repositories/{id}/report Get analysis report
POST   /api/v1/chat                    Conversational Q&A
POST   /api/v1/review                  Code review request
GET    /api/v1/audit-log               Audit trail
POST   /api/v1/auth/login              Authenticate
POST   /api/v1/auth/refresh            Refresh token
```

---

## 14. Planned: Phase 10 — Production Architecture

**Status:** Planned (not yet implemented)

### Required Components

- **Kubernetes** — Helm charts for all services
- **CI/CD** — GitHub Actions pipeline (test, build, push, deploy)
- **OpenTelemetry** — Distributed tracing across all services
- **Prometheus + Grafana** — Metrics collection and dashboards
- **Evaluation framework** — RAG answer quality scoring
- **Benchmarking** — Load testing + latency profiling
- **Incremental indexing** — Change detection via content hashes, re-index only changed files
- **Distributed processing** — Horizontal scaling for large repositories (> 10k files)

---

## 4. Step-by-Step Setup

### Step 1 — Prerequisites

- **Python 3.12 or higher** — [python.org/downloads](https://www.python.org/downloads/)
- **API key** for at least one LLM provider:
  - Google Gemini: [aistudio.google.com](https://aistudio.google.com/)
  - OpenAI: [platform.openai.com](https://platform.openai.com/)
  - Anthropic: [console.anthropic.com](https://console.anthropic.com/)
- `C:/temp` folder must be writable (or change `OUTPUT_DIR` in `src/doc_generator.py`).

### Step 2 — Install

```bash
# Open a terminal in the project folder

# Create and activate a virtual environment
python -m venv .venv

.venv\Scripts\activate      # Windows
source .venv/bin/activate   # Mac / Linux

# Install all dependencies (includes python-docx for .docx generation)
pip install -r requirements.txt
```

### Step 3 — Create `.env`

Create a file named `.env` in the project root.
Copy the template below and fill in your API key:

```env
# ── Choose ONE LLM provider ─────────────────────────────────────────────

# Option A: Google Gemini (default)
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
GOOGLE_API_KEY=your-google-api-key-here

# Option B: OpenAI
# LLM_PROVIDER=openai
# LLM_MODEL=gpt-4o
# OPENAI_API_KEY=your-openai-api-key-here

# Option C: Anthropic Claude
# LLM_PROVIDER=anthropic
# LLM_MODEL=claude-sonnet-4-5
# ANTHROPIC_API_KEY=your-anthropic-api-key-here

# ── Optional LLM tuning ─────────────────────────────────────────────────
# LLM_TEMPERATURE=0.1
# LLM_MAX_TOKENS=4096

# ── Phase 9: Enterprise REST API ────────────────────────────────────────
# Use SQLite for local development (no PostgreSQL needed):
# PLATFORM_DATABASE_URL=sqlite:///./java_intelligence.db
# PLATFORM_SECRET_KEY=your-32-character-minimum-secret-key
# PLATFORM_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
# PLATFORM_BOOTSTRAP_ADMIN_USERNAME=admin
# PLATFORM_BOOTSTRAP_ADMIN_PASSWORD=ChangeMe123!
```

> **Embedding model:** On first run `sentence-transformers` downloads the BGE model
> (~400 MB) to `~/.cache/huggingface/`. Subsequent runs are fully offline.

### Step 4 — Run

```bash
python run.py
```

That's it. `run.py` will guide you through the rest interactively.

---

## 5. Running the Platform

### Primary entry point: `python run.py`

`run.py` is the recommended way to use the platform. It runs the full pipeline
automatically and provides an interactive guide.

**What happens when you run `python run.py`:**

```
Step 1  Check for existing analysis data in data/
         ├── If found  → use it (shows file count)
         └── If not found → prompt for Java repo path, then run:
                            Phase 1 (ingest) → Phase 2 (vectors)
                            → Phase 4 (dependencies) → Phase 5 (architecture)

Step 2  User Profiling prompts (one by one, numbered options displayed):
         • Your Name
         • Your Role
         • Your Programming Knowledge
         • Your Java Expertise
         • Purpose of Analysis
         • Expected Depth
         → Computes knowledge level: beginner / intermediate / advanced / expert

Step 3  Generate personalised .docx report
         → Saved to C:/temp/JavaIntelligence_<Name>_<Level>_<Timestamp>.docx

Step 4  Start interactive Q&A chat mode
         → Type questions about the codebase
         → 'clear' to reset history, 'exit' to quit
```

### Option B — REST API (Phase 9)

```bash
# Start the server
uvicorn src.platform.main:app --reload --port 8000

# Browse interactive docs
start http://localhost:8000/docs    # Windows
open  http://localhost:8000/docs    # Mac
```

```bash
# Register, login, and run analysis via curl
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","email":"alice@co.com","password":"Pass1234!","full_name":"Alice"}'

TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"Pass1234!"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/api/v1/repositories \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"my-app","local_path":"/path/to/spring-app"}'

curl -X POST http://localhost:8000/api/v1/repositories/1/scan \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"job_type":"full_scan"}'

curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"What are the main services?","repository_id":1,"use_agents":true}'
```

---

## 6. User Profiling and Personalised Documentation

`python run.py` asks you six questions and then generates a `.docx` report tailored
to your background. Each field shows the accepted values before you enter a number.

| Field | Accepted values |
|---|---|
| **Role** | Developer · Senior Developer · Tech Lead · Architect · Engineering Manager · QA · DevOps · Product Owner · New Joiner |
| **Programming Knowledge** | Beginner · Intermediate · Advanced |
| **Java Expertise** | Beginner · Intermediate · Advanced · Expert |
| **Purpose of Analysis** | High-Level Overview · Technical Specification · Knowledge Transfer · Onboarding · Code Review · Bug Investigation · Migration Assessment · Architecture Assessment · Security Review · Performance Review · Dependency Analysis |
| **Expected Depth** | Executive Summary · Functional Overview · Technical Overview · Deep Technical Analysis · Expert Level Analysis |

### Knowledge level scoring

A composite score is computed from Role + Java Expertise + Expected Depth (max 11):

| Score | Level | `.docx` contains |
|---|---|---|
| 0–3 | **Beginner** | Plain-language overview, getting-started guide, glossary |
| 4–6 | **Intermediate** | Architecture layers, Spring patterns, component map, modules |
| 7–9 | **Advanced** | + Dependency analysis, request flow, coupling metrics, tech debt |
| 10–11 | **Expert** | + C4 model, security findings, SOLID violations, recommendations |

The `.docx` file is saved to `C:/temp/JavaIntelligence_<Name>_<Level>_<Date>.docx`.

---

## 7. Optional: Individual Phase Scripts

You can run each analysis phase independently if needed:

```bash
# Phase 1 — Ingest a Java repository
python main.py

# Phase 2 — Build / refresh vector index
python build_vector_db.py

# Phase 4 — Build dependency graph
python build_dependency_graph.py

# Phase 5 — Architecture report + Mermaid diagrams + C4 model + onboarding doc
python build_architecture.py
python build_architecture.py --llm           # LLM-generated narrative summaries
python build_architecture.py --app-name MyApp

# Phase 6 — Single-agent REPL
python run_agent.py
python run_agent.py --question "Which classes depend on CustomerRepository?"
python run_agent.py --verbose

# Phase 7 — Multi-agent REPL
python run_multi_agent.py
python run_multi_agent.py --question "What are the architectural layers?"
python run_multi_agent.py --verbose

# Phase 3 — Chat only
python src/chat.py

# Simple semantic search
python search.py

# Phase 4 demo with sample_spring_repo
python run_dependency_demo.py
```

### Phase dependency chain

```
main.py  (Phase 1: ingest)
  └─▶ build_vector_db.py  (Phase 2: vectors)
  └─▶ build_dependency_graph.py  (Phase 4: dependencies)
  └─▶ build_architecture.py  (Phase 5: architecture)
        └─▶ run_agent.py / run_multi_agent.py

python run.py  ← runs Phases 1+2+4+5 automatically if data is missing,
               then profiles you, generates .docx, and enters chat mode.
```

---

## 8. REST API (Phase 9)

```bash
# Development server
uvicorn src.platform.main:app --reload --port 8000

# Production (4 workers)
gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.platform.main:app --bind 0.0.0.0:8000
```

| Method | Endpoint | Description | Min Role |
|---|---|---|---|
| POST | `/api/v1/auth/register` | Create account | — |
| POST | `/api/v1/auth/login` | Get JWT tokens | — |
| POST | `/api/v1/auth/refresh` | Refresh access token | — |
| GET | `/api/v1/repositories` | List repos | viewer |
| POST | `/api/v1/repositories` | Register repo | analyst |
| POST | `/api/v1/repositories/{id}/scan` | Trigger analysis job | analyst |
| GET | `/api/v1/repositories/{id}/review` | Code review report | viewer |
| GET | `/api/v1/repositories/{id}/onboarding` | Onboarding doc | viewer |
| POST | `/api/v1/chat` | Ask a question | viewer |
| GET | `/api/v1/audit` | Audit trail | admin |

---

## 9. Testing

```bash
# All tests (106 total)
python -m pytest -q

# Phase 8 code review (45 tests)
python -m pytest test_code_review.py -v

# Phase 9 platform API (61 tests)
python -m pytest test_platform.py -v

# Integration pipeline
python -m pytest test_pipeline.py -v

# Specific test class
python -m pytest test_code_review.py::TestSecurityAnalyzer -v

# With coverage report
python -m pytest test_code_review.py --cov=src/code_review --cov-report=term-missing
```

| Suite | File | Tests | Scope |
|---|---|---|---|
| Phase 8 | `test_code_review.py` | 45 | All 7 analyzers, scoring engine, tools, prompts |
| Phase 9 | `test_platform.py` | 61 | Auth, users, repos, jobs, RBAC, audit |
| **Total** | | **106** | |

### Phase 8 Coverage by Module

| Module            | Tests | Coverage Areas                                          |
|-------------------|-------|---------------------------------------------------------|
| `models.py`       | 5     | Severity enum, finding serialisation, report formatting |
| `engine.py`       | 8     | Score calc, grading, dedup, category summaries, filters  |
| `solid.py`        | 5     | SRP/OCP/LSP/DIP detection, clean class baseline         |
| `security.py`     | 4     | SQL injection, hardcoded creds, weak crypto, clean class|
| `performance.py`  | 3     | N+1, findAll pagination, eager fetch                    |
| `maintainability.py`| 3   | Empty catch, deep nesting, public fields                |
| `tech_debt.py`    | 4     | TODO comments, missing tests, test-present baseline     |
| `duplicates.py`   | 1     | Structural clone detection                              |
| `patterns.py`     | 3     | God class, Service Locator, anemic model                |
| `tools.py`        | 2     | Tool registration, tool API contract                    |
| `prompts.py`      | 4     | Prompt building, JSON parsing, error handling           |

---

## 17. Data Assets

All generated assets are stored in `data/` and are produced by the build scripts:

| File                        | Producer                  | Consumer                              |
|-----------------------------|---------------------------|---------------------------------------|
| `repository_metadata.json`  | Phase 1 (scanner)         | All phases                            |
| `dependency_graph.json`     | Phase 4 (dependency)      | Phase 4 tools, architecture           |
| `dependency_adjacency.json` | Phase 4                   | Reporting                             |
| `architecture_report.json`  | Phase 5 (architecture)    | Phase 5 tools, coordinator            |
| `architecture_c4.txt`       | Phase 5                   | Documentation, onboarding             |
| `architecture_diagrams.md`  | Phase 5                   | Documentation                         |
| `onboarding.md`             | Phase 5                   | `get_documentation` tool              |

---

## 18. Configuration

### LLM Provider (`src/llm.py`)

Set in `.env` — no code changes needed:

| Variable | Default | Options |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini`, `openai`, `anthropic` |
| `LLM_MODEL` | `gemini-2.5-flash` | any model name for the chosen provider |
| `LLM_TEMPERATURE` | `0.1` | `0.0` – `1.0` |
| `LLM_MAX_TOKENS` | `4096` | any positive integer |
| `LLM_CONDENSE_MAX_TOKENS` | `256` | token cap for the follow-up condenser |

Verify the active provider:
```bash
python -c "from src.llm import get_active_provider; print(get_active_provider())"
```

### `AgentConfig` (`src/agent/config.py`)

```python
@dataclass
class AgentConfig:
    model: str = "gemini-2.5-flash"
    temperature: float = 0.1
    max_output_tokens: int = 8192
    max_retries: int = 3
    retrieval_k: int = 8
    retrieval_fetch_k: int = 30
    use_hybrid_retrieval: bool = True
    max_iterations: int = 10
    memory_window: int = 6
```

### `CodeReviewEngine` Options

```python
CodeReviewEngine(
    repo_root="/path/to/repo",        # base path for resolving file paths
    enabled_analyzers=[               # omit for all
        "solid", "security",
        "performance", "maintainability",
        "duplicates", "tech_debt", "patterns",
    ],
)
```

---

## 19. Constraints and Design Decisions

### Must Support

- Spring Boot projects (mono-repo and multi-module)
- Multi-module Maven and Gradle projects
- Monoliths and modular monoliths
- Large repositories (> 10,000 Java files)

### Design Decisions

| Decision                              | Rationale                                                  |
|---------------------------------------|------------------------------------------------------------|
| Static regex analysis (not AST)       | No tree-sitter dependency for review; faster; works on metadata alone |
| Metadata-first analysis               | Content reading is lazy (only when file exists); survives partial repos |
| Severity scoring model                | Weighted penalty scaled by class count for fair cross-repo comparison |
| LLM pass is optional                  | Static analysis works standalone; LLM enriches but doesn't block |
| All tools are LangChain `@tool`       | Seamless integration with existing agent infrastructure |
| `_merge_dicts` reducer in state       | Enables safe parallel agent writes in LangGraph Send API |
| Pydantic v2 models                    | Type safety, JSON serialisation, validation at module boundary |
| No re-indexing without change         | Content hashes in metadata enable incremental processing |
| Sync SQLAlchemy (not async)           | Compatibility with LangChain / NetworkX which are inherently synchronous |
| bcrypt directly (not passlib)         | passlib is not compatible with bcrypt >= 4.x |
| FastAPI BackgroundTasks (no Celery)   | Simple single-process deployment; no Redis / worker processes needed |
| Per-repo ChromaDB collection          | `repo_{id}` collection name isolates multi-repo vector indices |

---

## 13. Phase 9 — Enterprise Platform

Phase 9 adds a production-ready REST API layer with authentication, role-based access control, multi-repository support, background analysis jobs, and a full audit trail.

### Architecture Overview

```
FastAPI app  (src/platform/main.py)
│
├── /api/v1/auth          JWT login, register, refresh, logout
├── /api/v1/users         User CRUD, role management, password change
├── /api/v1/repositories  Repository registration, scan jobs, report access
├── /api/v1/chat          Per-repository RAG / multi-agent Q&A
├── /api/v1/review        On-demand Phase 8 code review
└── /api/v1/audit         Immutable audit trail (admin only)
│
├── src/platform/
│   ├── config.py          PlatformSettings (pydantic-settings, PLATFORM_ prefix)
│   ├── database.py        SQLAlchemy engine + session + Base
│   ├── main.py            FastAPI factory, lifespan, CORS, bootstrap admin
│   ├── auth/              JWT (python-jose), bcrypt, RBAC dependencies
│   ├── models/            SQLAlchemy 2.0 ORM models (User, Repository, AuditLog)
│   ├── schemas/           Pydantic v2 request/response schemas
│   ├── services/          Business logic services (user, repo, audit)
│   ├── jobs/              Background analysis pipeline (Phases 1-8)
│   └── api/v1/            FastAPI routers
```

### Setup

All Phase 9 dependencies are already included in `requirements.txt`.

```bash
pip install -r requirements.txt
```

Add platform variables to `.env` (all optional — defaults to SQLite + a dev secret key):
```dotenv
PLATFORM_DATABASE_URL=postgresql://user:pass@localhost:5432/java_intelligence
PLATFORM_SECRET_KEY=your-32-char-minimum-secret-key
PLATFORM_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
PLATFORM_BOOTSTRAP_ADMIN_USERNAME=admin
PLATFORM_BOOTSTRAP_ADMIN_PASSWORD=SecurePass123!
```

Start the server:
```bash
uvicorn src.platform.main:app --reload --port 8000
# Interactive API docs → http://localhost:8000/docs
```

### RBAC Matrix

| Action                        | viewer | analyst | admin |
|-------------------------------|:------:|:-------:|:-----:|
| Register / login              | ✓      | ✓       | ✓     |
| List own repositories         | ✓      | ✓       | ✓     |
| Chat / Q&A                    | ✓      | ✓       | ✓     |
| Register new repository       |        | ✓       | ✓     |
| Trigger analysis jobs         |        | ✓       | ✓     |
| Grant/revoke repo access      |        | ✓       | ✓     |
| Trigger code review           |        | ✓       | ✓     |
| List all users                |        |         | ✓     |
| Create / deactivate users     |        |         | ✓     |
| Change user roles             |        |         | ✓     |
| Delete repositories           |        |         | ✓     |
| View audit logs               |        |         | ✓     |

### Database Schema

| Table             | Purpose                                            |
|-------------------|----------------------------------------------------|
| `users`           | User accounts with bcrypt-hashed passwords         |
| `repositories`    | Registered repos with lifecycle status             |
| `repository_access` | Explicit per-user read/write/admin grants        |
| `analysis_jobs`   | Background job tracking (pending/running/done)     |
| `audit_logs`      | Immutable append-only event trail                  |

### Background Analysis Pipeline

Triggered via `POST /api/v1/repositories/{id}/scan`:

```
FULL_SCAN (default)
  Step 1: METADATA      → Phase 1 Java AST parser → metadata.json
  Step 2: VECTOR_INDEX  → Phase 2 ChromaDB per-repo → vectordb/
  Step 3: DEPENDENCY    → Phase 4 dependency graph → dependency_graph.json
  Step 4: ARCHITECTURE  → Phase 5 C4 analysis → architecture_report.json
  Step 5: CODE_REVIEW   → Phase 8 static review → code_review_report.json
```

Each step can also be triggered independently (job_type = `metadata|vector_index|dependency|architecture|code_review`).

Per-repository data is stored under `data/repositories/{repo_id}/`.

### Multi-Repository Support

Each repository gets an isolated data directory and its own ChromaDB collection (`repo_{id}`). This allows multiple repositories to be indexed simultaneously without cross-contamination.

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Sync SQLAlchemy (not async) | Compatibility with LangChain / NetworkX which are sync |
| FastAPI BackgroundTasks (no Celery) | Simple deployment — no Redis/worker processes needed |
| bcrypt directly (not passlib) | passlib not compatible with bcrypt >= 4.x |
| Per-repo ChromaDB collection | Enables multi-repo vector isolation |
| JWT JTI claim | Foundation for token revocation (Phase 10 Redis blocklist) |

### Tests

```bash
python -m pytest test_platform.py -q
# 61 passed in ~30s
```

Test classes: `TestAuth`, `TestUsers`, `TestRepositories`, `TestAuditLog`, `TestRBAC`, `TestChat`, `TestAnalysisJobPipeline`, `TestPlatformServices`.

---

*Last updated: Phase 9 complete, multi-provider LLM — June 2026*
