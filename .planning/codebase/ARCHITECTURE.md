<!-- refreshed: 2026-07-16 -->
# Architecture

**Analysis Date:** 2026-07-16

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                      Presentation Layer                      │
├──────────────────────────────┬──────────────────────────────┤
│   Streamlit UI               │   FastAPI REST API            │
│  `ui/app.py`                 │  `api/main.py`                │
└──────────────┬───────────────┴──────────────┬───────────────┘
               │ HTTP POST /query              │
               ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    RAG Orchestration Layer                   │
│         `rag/pipeline.py` (RAGPipeline)                      │
│   rewrite → retrieve → generate → log                        │
├───────────────┬──────────────┬──────────────┬───────────────┤
│  QueryRewriter│ HybridRetriever│  LLMGenerator│  QueryLogger  │
│ `rag/rewriter`│ `rag/retrieval`│ `rag/generator`│`monitoring/  │
│               │                │              │  logging`     │
└───────┬───────┴───────┬────────┴──────┬───────┴───────┬───────┘
        │               │               │               │
        ▼               ▼               ▼               ▼
┌────────────┐   ┌────────────┐  ┌────────────┐  ┌────────────┐
│ static map │   │  Qdrant    │  │  OpenAI    │  │ PostgreSQL │
│ (threat ID)│   │ vector DB  │  │  API       │  │ + Grafana  │
└────────────┘   └────────────┘  └────────────┘  └────────────┘

┌─────────────────────────────────────────────────────────────┐
│              Offline Ingestion Layer (dlt)                   │
│  `ingestion/run_pipeline.py`                                 │
│  sources → chunk → embed → Qdrant                            │
└─────────────────────────────────────────────────────────────┘
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

**Overall:** Layered RAG (Retrieval-Augmented Generation) service with a separate offline ingestion pipeline.

**Key Characteristics:**
- Clear separation between online serving (`rag/`, `api/`, `ui/`) and offline ingestion (`ingestion/`).
- Pipeline composed of single-responsibility classes injected into `RAGPipeline`.
- Async streaming end-to-end (generator → API `StreamingResponse` → UI).
- Externalized state: Qdrant (vectors), PostgreSQL (logs/metrics), OpenAI (generation/embeddings).
- Much of the implementation is scaffolded with placeholders returning empty/mock results (see CONCERNS).

## Layers

**Presentation:**
- Purpose: Accept user queries, display streamed answers, collect feedback.
- Location: `ui/app.py` (Streamlit), `api/main.py` (FastAPI).
- Depends on: RAG orchestration layer.

**RAG Orchestration:**
- Purpose: Run the full query lifecycle.
- Location: `rag/pipeline.py`.
- Contains: composition of rewriter, retriever, generator, logger.
- Used by: `api/main.py` (lazy-imported inside `/query`).

**Retrieval / Generation / Rewriting:**
- Purpose: Individual RAG steps.
- Location: `rag/retrieval.py`, `rag/generator.py`, `rag/rewriter.py`.
- Depends on: Qdrant client, OpenAI async client, static mapping dict.

**Monitoring:**
- Purpose: Persist query logs, feedback, expose metrics.
- Location: `monitoring/logging.py`, `monitoring/metrics.py`.
- Consumed by: Grafana via PostgreSQL datasource (`monitoring/grafana/provisioning/`).

**Ingestion (offline):**
- Purpose: Build the Qdrant corpus.
- Location: `ingestion/`.
- Used by: run manually before serving.

## Data Flow

### Primary Request Path (query)

1. Client submits query to `POST /query` (`api/main.py:50`)
2. `RAGPipeline` instantiated and `stream_answer` invoked (`rag/pipeline.py:21`)
3. Query rewritten to threat ID if matched (`rag/rewriter.py:37`)
4. Context retrieved from Qdrant (`rag/retrieval.py:59`) — currently placeholder returns `[]` (`rag/pipeline.py:40`)
5. Answer streamed token-by-token from OpenAI (`rag/generator.py:15`)
6. Tokens streamed to client via `StreamingResponse` (`api/main.py:72`)
7. Query metadata logged after stream completes (`rag/pipeline.py:57`, `monitoring/logging.py:25`)

### Feedback Path

1. Client submits to `POST /feedback` (`api/main.py:79`)
2. `QueryLogger.log_feedback` records signal (`monitoring/logging.py:52`)

### Ingestion Flow (offline)

1. `run_pipeline.py` connects to Qdrant, ensures collection (`ingestion/run_pipeline.py:47`)
2. dlt sources fetch corpora (`ingestion/dlt_sources/*.py`)
3. Documents chunked (`ingestion/transforms/chunk.py`) and embedded (`ingestion/transforms/embed.py`)
4. Vectors (dim 512, cosine) loaded into Qdrant collection

**State Management:**
- No in-process state; every request builds a fresh `RAGPipeline`. Durable state lives in Qdrant and PostgreSQL.

## Key Abstractions

**Retriever hierarchy:**
- Purpose: Pluggable retrieval strategies.
- Examples: `DenseRetriever`, `BM25Retriever`, `HybridRetriever` in `rag/retrieval.py`.
- Pattern: Composition — `HybridRetriever` wraps dense + BM25.

**Prompt variants:**
- Purpose: A/B comparison of answer framing.
- Examples: `"base"` and `"practitioner"` in `rag/generator.py:27`.
- Pattern: Branch on `prompt_variant` string.

**Threat ID mapping:**
- Purpose: Normalize free text to canonical IDs (LLM01, AGENTIC-01, MCP-security).
- Examples: `QueryRewriter.THREAT_MAPPINGS` in `rag/rewriter.py:10`.

## Entry Points

**FastAPI server:**
- Location: `api/main.py:111`
- Triggers: `python api/main.py` / uvicorn (`api.main:app`)
- Responsibilities: Serve `/query`, `/feedback`, `/health`, `/metrics`.

**Streamlit UI:**
- Location: `ui/app.py`
- Triggers: `streamlit run ui/app.py`
- Responsibilities: Browser-based query interface.

**Ingestion pipeline:**
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

**What happens:** Retrieval and logging return empty lists / log-only stubs (`rag/pipeline.py:40`, `rag/retrieval.py:48`, `monitoring/logging.py:49`).
**Why it's wrong:** The pipeline runs green but retrieves no context; answers are ungrounded.
**Do this instead:** Wire the retriever output into `RAGPipeline.stream_answer` (embed query → `HybridRetriever.retrieve`) before treating the path as functional.

### Per-request client construction

**What happens:** A new `QdrantClient` and `AsyncOpenAI` are created on every `RAGPipeline()` (once per request).
**Why it's wrong:** Connection overhead per query; no pooling.
**Do this instead:** Instantiate clients once at app startup (FastAPI lifespan) and inject.

## Error Handling

**Strategy:** Try/except at endpoint boundaries returning HTTP 500 (`api/main.py:74`); retrievers swallow exceptions and return `[]` (`rag/retrieval.py:36`); generator yields an error string into the stream (`rag/generator.py:64`).

**Patterns:**
- Endpoint-level exception → `HTTPException(500)`.
- Retrieval failures degrade to empty results (silent).
- Generation failures surface as an inline error token.

## Cross-Cutting Concerns

**Logging:** Python `logging` (stdlib) configured at module load (`api/main.py:14`, `ingestion/run_pipeline.py:16`); query logging via `QueryLogger`.
**Validation:** Pydantic `BaseModel` request models (`api/main.py:24`); prompt variant validated in generator (`rag/generator.py:46`).
**Authentication:** None implemented on API or UI.

---

*Architecture analysis: 2026-07-16*
