<!-- GSD:project-start source:PROJECT.md -->

## Project

**Security RAG Assistant (LLM Zoomcamp 2026 Capstone)**

A retrieval-augmented generation assistant that answers AI/LLM security questions grounded in authoritative sources (OWASP LLM Top 10, OWASP Agentic Top 10, MCP protocol spec, MCP security docs, NIST AI RMF). For security engineers and practitioners who need cited, framework-anchored answers about LLM/agent threats and mitigations. Built as the LLM Zoomcamp 2026 capstone submission.

**Core Value:** Ask a security question, get an accurate answer grounded in real retrieved source passages (not the model's parametric memory) with threat IDs and citations. If retrieval doesn't actually work end-to-end, nothing else matters.

### Constraints

- **Tech stack (locked)**: Qdrant (vectors), OpenAI API gpt-4o / gpt-4o-mini, dlt (ingestion), 5 security sources — do not swap.
- **Deployment**: Local Docker only — no external hosting (org policy).
- **Timeline**: Submission by end of LLM Zoomcamp 2026 cohort (late July / early August 2026).
- **Testing**: Pragmatic — tests on load-bearing logic, not exhaustive coverage; fit the deadline.
- **Embedding**: OpenAI `text-embedding-3-small`; embedding dimension must match between ingest and Qdrant collection.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3.11 - All application code (`api/`, `rag/`, `ingestion/`, `evaluation/`, `monitoring/`, `ui/`)
- SQL (PostgreSQL dialect) - Query logging, dlt destination
- JSON/YAML - Grafana provisioning (`monitoring/grafana/provisioning/`)

## Runtime

- Python 3.11 (`python:3.11-slim` base image in `Dockerfile`)
- pip
- Lockfile: missing (pinned versions in `requirements.txt`, no `requirements.lock`/`uv.lock`)

## Frameworks

- FastAPI 0.109.0 - HTTP API (`api/main.py`), served by uvicorn
- Streamlit 1.28.1 - User-facing chat UI (`ui/app.py`)
- dlt 0.5.0 `[postgres,requests,connectors]` - Orchestrated ingestion pipeline (`ingestion/run_pipeline.py`)
- scikit-learn 1.3.2 - Retrieval/eval metrics (`evaluation/`)
- No dedicated test framework detected (no pytest/jest in `requirements.txt`)
- uvicorn[standard] 0.27.0 - ASGI server (container `CMD`)
- Docker / docker-compose 3.8 - Local orchestration (`docker-compose.yml`)

## Key Dependencies

- openai 1.6.1 - LLM generation (`gpt-4o-mini`) and embeddings (`text-embedding-3-small`, 512-dim); see `rag/generator.py`, `ingestion/transforms/embed.py`
- qdrant-client 2.7.0 - Vector search (`rag/retrieval.py`)
- sentence-transformers 2.2.2 - Local embedding / reranking models
- rank-bm25 0.2.2 - BM25 sparse retrieval (`rag/retrieval.py`)
- pydantic 2.5.0 / pydantic-settings 2.1.0 - Config and request/response models
- pandas 2.1.4, numpy 1.24.3
- PyPDF2 4.0.1 - NIST AI RMF PDF parsing (`ingestion/dlt_sources/nist_ai_rmf.py`)
- beautifulsoup4 4.12.2, markdownify 0.11.6 - HTML → markdown
- requests 2.31.0, httpx 0.25.2 - HTTP clients
- psycopg2-binary 2.9.9, SQLAlchemy 2.0.23 - PostgreSQL access / query logging (`monitoring/logging.py`)
- prometheus-client 0.19.0 - Metrics (`monitoring/metrics.py`)
- python-dotenv 1.0.1 - `.env` loading

## Configuration

- `.env` file (template: `.env.example`) loaded via python-dotenv
- Key configs: `OPENAI_API_KEY`, `POSTGRES_URL` / `DLT_POSTGRES_*`, `QDRANT_HOST`/`QDRANT_PORT`/`QDRANT_COLLECTION_NAME`, `API_HOST`/`API_PORT`, `STREAMLIT_PORT`, `ENVIRONMENT`, `LOG_LEVEL`
- Config read directly via `os.getenv()` in modules; pydantic-settings available but wiring not centralized
- `Dockerfile` - installs system deps (git, curl, build-essential, postgresql-client) then `requirements.txt`
- `docker-compose.yml` - services: postgres (15-alpine), qdrant (latest), grafana (latest), app

## Platform Requirements

- Docker + docker-compose, or local Python 3.11 with running Postgres and Qdrant
- Container image exposes ports 8000 (FastAPI) and 8501 (Streamlit); default `CMD` runs the API only

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Naming Patterns

- `snake_case.py` for all modules (`rag/pipeline.py`, `ingestion/transforms/chunk.py`)
- Package dirs are lowercase single words (`rag/`, `api/`, `ingestion/`, `monitoring/`, `evaluation/`, `ui/`)
- Each package has an `__init__.py` (currently empty markers)
- dlt source modules named by data source (`ingestion/dlt_sources/owasp_llm.py`, `nist_ai_rmf.py`)
- `snake_case` (`stream_answer`, `log_query`, `chunk_by_sections`, `normalize_threat_id`)
- Async functions prefixed conceptually by streaming intent (`stream_answer`, `answer_generator`)
- Private helpers prefixed with `_` (`_init_tables`)
- `snake_case` (`retrieval_latency_ms`, `prompt_variant`, `query_lower`)
- Latency/measurement vars carry unit suffix (`_ms`) — `retrieval_latency_ms`, `total_latency_ms`
- `PascalCase` (`RAGPipeline`, `HybridRetriever`, `QueryLogger`, `LLMGenerator`, `Chunker`)
- Pydantic models use noun + role suffix (`QueryRequest`, `HealthResponse` in `api/main.py`)
- Class-level constants `UPPER_SNAKE` (`THREAT_MAPPINGS` in `rag/rewriter.py`)

## Code Style

- No formatter configured (no `pyproject.toml`, `ruff.toml`, `.flake8`, `setup.cfg` present)
- De facto 4-space indent, double-quoted strings, ~100 char lines
- Multi-line function signatures with one arg per line when long (`RAGPipeline.stream_answer`, `QueryLogger.log_query`)
- Not detected — no linter config in repo. Recommend adding `ruff` before growth.

## Import Organization

- None. Absolute package imports from repo root (`rag.pipeline`, `monitoring.logging`).
- Lazy imports used inside route handlers to avoid circular deps (`api/main.py` imports `RAGPipeline` inside `query_endpoint`). Note the comment `# lazy import to avoid circular dependencies`.

## Error Handling

- Broad `try/except Exception as e` around external calls (OpenAI, Qdrant, route handlers)
- Two divergent styles — reconcile before scaling:
- `ValueError` raised for invalid enum-like input (`raise ValueError(f"Unknown prompt variant: {prompt_variant}")` in `rag/generator.py`)
- Existence checks before file reads (`evaluation/eval_retrieval.py` `load_ground_truth`)

## Logging

- Module-level `logger` per file (`monitoring/logging.py`, `api/main.py`)
- Structured payloads logged as JSON strings (`logger.info(f"Query logged: {json.dumps(log_entry)}")`)
- Some library code uses `print(...)` for errors (`DenseRetriever.retrieve`, `evaluation/eval_retrieval.py`) — inconsistent with the logging convention; prefer `logger` in new code.

## Comments

- Inline comments flag placeholders/stubs heavily (`# Placeholder: would write to postgres`, `# Would be populated from actual retriever`). These mark unfinished integration points.
- Step comments narrate pipeline flow (`# Step 1: Rewrite query` ... `# Step 4: Log query`)
- Every module opens with a one-line `"""..."""` module docstring
- Every class and public method has a docstring; some are full multi-line with behavior notes (`LLMGenerator.stream_answer` documents prompt variants), many are one-liners
- Not Google-style structured (no `Args:`/`Returns:`/`Raises:` sections). New public functions should adopt Google-style docstrings per project standard.

## Function Design

- Keyword args with defaults for optional config (`top_k: int = 5`, `prompt_variant: str = "base"`, `user_id: str = None`)
- Type hints on all params and returns (`List[Dict[str, Any]]`, `AsyncGenerator[str, None]`, `Tuple[str, str]`)
- Note: `user_id: str = None` uses `None` default without `Optional[...]` in some signatures (`api/main.py`, `rag/pipeline.py`); `monitoring/logging.py` correctly uses `Optional[str]`. Prefer `Optional[...]` for None-defaulted params.
- Retrievers/chunkers return `List[Dict[str, Any]]` with `{"text", "score", "metadata"}` or `{"text", "metadata"}` shape
- Streaming generators `yield` string tokens
- Config read from env with defaults (`os.getenv("QDRANT_PORT", 6333)`, `os.getenv("QDRANT_COLLECTION_NAME", "security_rag")`)

## Module Design

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Streamlit UI | Interactive query interface, feedback buttons | `ui/app.py` |
| FastAPI app | REST endpoints, streaming responses | `api/main.py` |
| RAGPipeline | Orchestrate rewrite→retrieve→generate→log | `rag/pipeline.py` |
| QueryRewriter | Map free text to canonical threat IDs | `rag/rewriter.py` |
| HybridRetriever | Dense + BM25 retrieval with RRF fusion | `rag/retrieval.py` |
| LLMGenerator | OpenAI streaming generation, prompt variants | `rag/generator.py` |
| QueryLogger / MetricsCollector | Log queries/feedback, expose metrics | `monitoring/logging.py`, `monitoring/metrics.py` |
| Ingestion pipeline | Fetch, chunk, embed, load sources into Qdrant | `ingestion/run_pipeline.py` |
| dlt sources | Per-corpus extraction (OWASP, MCP, NIST) | `ingestion/dlt_sources/*.py` |
| Transforms | Chunking and embedding | `ingestion/transforms/chunk.py`, `ingestion/transforms/embed.py` |

## Pattern Overview

- Clear separation between online serving (`rag/`, `api/`, `ui/`) and offline ingestion (`ingestion/`).
- Pipeline composed of single-responsibility classes injected into `RAGPipeline`.
- Async streaming end-to-end (generator → API `StreamingResponse` → UI).
- Externalized state: Qdrant (vectors), PostgreSQL (logs/metrics), OpenAI (generation/embeddings).
- Much of the implementation is scaffolded with placeholders returning empty/mock results (see CONCERNS).

## Layers

- Purpose: Accept user queries, display streamed answers, collect feedback.
- Location: `ui/app.py` (Streamlit), `api/main.py` (FastAPI).
- Depends on: RAG orchestration layer.
- Purpose: Run the full query lifecycle.
- Location: `rag/pipeline.py`.
- Contains: composition of rewriter, retriever, generator, logger.
- Used by: `api/main.py` (lazy-imported inside `/query`).
- Purpose: Individual RAG steps.
- Location: `rag/retrieval.py`, `rag/generator.py`, `rag/rewriter.py`.
- Depends on: Qdrant client, OpenAI async client, static mapping dict.
- Purpose: Persist query logs, feedback, expose metrics.
- Location: `monitoring/logging.py`, `monitoring/metrics.py`.
- Consumed by: Grafana via PostgreSQL datasource (`monitoring/grafana/provisioning/`).
- Purpose: Build the Qdrant corpus.
- Location: `ingestion/`.
- Used by: run manually before serving.

## Data Flow

### Primary Request Path (query)

### Feedback Path

### Ingestion Flow (offline)

- No in-process state; every request builds a fresh `RAGPipeline`. Durable state lives in Qdrant and PostgreSQL.

## Key Abstractions

- Purpose: Pluggable retrieval strategies.
- Examples: `DenseRetriever`, `BM25Retriever`, `HybridRetriever` in `rag/retrieval.py`.
- Pattern: Composition — `HybridRetriever` wraps dense + BM25.
- Purpose: A/B comparison of answer framing.
- Examples: `"base"` and `"practitioner"` in `rag/generator.py:27`.
- Pattern: Branch on `prompt_variant` string.
- Purpose: Normalize free text to canonical IDs (LLM01, AGENTIC-01, MCP-security).
- Examples: `QueryRewriter.THREAT_MAPPINGS` in `rag/rewriter.py:10`.

## Entry Points

- Location: `api/main.py:111`
- Triggers: `python api/main.py` / uvicorn (`api.main:app`)
- Responsibilities: Serve `/query`, `/feedback`, `/health`, `/metrics`.
- Location: `ui/app.py`
- Triggers: `streamlit run ui/app.py`
- Responsibilities: Browser-based query interface.
- Location: `ingestion/run_pipeline.py:108`
- Triggers: `python ingestion/run_pipeline.py [--sources all] [--clear-qdrant]`
- Responsibilities: Populate Qdrant.

## Architectural Constraints

- **Threading:** Async/await throughout serving path; FastAPI + uvicorn single event loop. OpenAI calls use `AsyncOpenAI`.
- **Global state:** FastAPI `app` is module-level (`api/main.py:17`). No shared mutable singletons in the pipeline — instances are per-request.
- **Circular imports:** `RAGPipeline` is lazy-imported inside the `/query` handler (`api/main.py:59`) to avoid import-time cycles.
- **External dependencies:** Requires Qdrant, PostgreSQL, and an `OPENAI_API_KEY` to function; retrievers construct a `QdrantClient` at init (`rag/retrieval.py:17`).
- **Embedding dimension:** Fixed at 512 (`ingestion/run_pipeline.py:65`) — must match embed transform output.

## Anti-Patterns

### Placeholder returns masquerading as implementation

### Per-request client construction

## Error Handling

- Endpoint-level exception → `HTTPException(500)`.
- Retrieval failures degrade to empty results (silent).
- Generation failures surface as an inline error token.

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
