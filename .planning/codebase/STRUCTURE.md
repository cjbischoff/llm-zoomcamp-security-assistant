# Codebase Structure

**Analysis Date:** 2026-07-16

## Directory Layout

```
llm-zoomcamp-security-assistant/
├── api/                    # FastAPI REST server (entry point)
│   ├── __init__.py
│   └── main.py
├── ui/                     # Streamlit web interface (entry point)
│   ├── __init__.py
│   └── app.py
├── rag/                    # Online RAG pipeline
│   ├── pipeline.py         # Orchestration: rewrite→retrieve→generate→log
│   ├── rewriter.py         # Threat ID normalization
│   ├── retrieval.py        # Dense / BM25 / Hybrid retrievers
│   └── generator.py        # OpenAI streaming generation
├── ingestion/              # Offline dlt ingestion pipeline
│   ├── run_pipeline.py     # Orchestration script (entry point)
│   ├── dlt_sources/        # Per-corpus source extractors
│   │   ├── owasp_llm.py
│   │   ├── owasp_agentic.py
│   │   ├── mcp_spec.py
│   │   ├── mcp_security.py
│   │   └── nist_ai_rmf.py
│   └── transforms/         # Chunking + embedding
│       ├── chunk.py
│       └── embed.py
├── evaluation/             # Eval framework
│   ├── generate_qa.py      # Ground-truth Q&A generation
│   ├── eval_retrieval.py   # Hit rate, MRR, Precision@5
│   └── eval_llm.py         # LLM-as-judge scoring
├── monitoring/             # Observability
│   ├── logging.py          # QueryLogger + MetricsCollector
│   ├── metrics.py          # Prometheus metrics
│   └── grafana/provisioning/  # Datasources + dashboard JSON
├── docker-compose.yml      # postgres, qdrant, grafana, app
├── Dockerfile              # App container
├── requirements.txt        # Python dependencies
├── .env.example            # Environment variable template
├── README.md
├── IMPLEMENTATION_CHECKLIST.md
└── PROJECT_MANIFEST.md
```

## Directory Purposes

**`api/`:**
- Purpose: HTTP serving layer.
- Contains: FastAPI app, Pydantic request models, endpoints.
- Key files: `api/main.py`

**`rag/`:**
- Purpose: Online query-answering pipeline.
- Contains: One class per pipeline step plus orchestrator.
- Key files: `rag/pipeline.py`

**`ingestion/`:**
- Purpose: Offline corpus building with dlt.
- Contains: source extractors and transforms.
- Key files: `ingestion/run_pipeline.py`

**`monitoring/`:**
- Purpose: Query logging, metrics, Grafana provisioning.
- Contains: logger, metrics, dashboards.
- Key files: `monitoring/logging.py`, `monitoring/grafana/provisioning/dashboards/security_rag_dashboard.json`

**`evaluation/`:**
- Purpose: Retrieval + generation quality measurement.

## Key File Locations

**Entry Points:**
- `api/main.py`: FastAPI server (`uvicorn api.main:app`)
- `ui/app.py`: Streamlit UI (`streamlit run ui/app.py`)
- `ingestion/run_pipeline.py`: Ingestion CLI

**Configuration:**
- `.env.example`: Env var template (Qdrant, PostgreSQL, OpenAI settings)
- `docker-compose.yml`: 4-service stack
- `requirements.txt`: Dependencies

**Core Logic:**
- `rag/pipeline.py`: RAG orchestration
- `rag/retrieval.py`: Retrieval strategies
- `rag/generator.py`: LLM generation

**Testing:**
- No test directory present (see CONCERNS).

## Naming Conventions

**Files:**
- snake_case module names: `run_pipeline.py`, `eval_retrieval.py`
- Package dirs have `__init__.py`

**Classes:**
- PascalCase: `RAGPipeline`, `HybridRetriever`, `QueryRewriter`, `LLMGenerator`

**Functions/methods:**
- snake_case: `stream_answer`, `log_query`, `run_pipeline`

**Directories:**
- Layer-named lowercase: `rag`, `ingestion`, `monitoring`, `evaluation`

## Where to Add New Code

**New retrieval strategy:**
- Add class to `rag/retrieval.py`, compose into `HybridRetriever`.

**New API endpoint:**
- Add route to `api/main.py`; define Pydantic model alongside existing ones.

**New ingestion source:**
- Add module to `ingestion/dlt_sources/`, register in `ingestion/run_pipeline.py`.

**New prompt variant:**
- Add branch in `rag/generator.py:27` `stream_answer`.

**New threat ID mapping:**
- Extend `QueryRewriter.THREAT_MAPPINGS` in `rag/rewriter.py:10`.

**Tests:**
- No convention established; recommend a top-level `tests/` mirroring package layout.

## Special Directories

**`monitoring/grafana/provisioning/`:**
- Purpose: Grafana datasource + dashboard config mounted into the container.
- Generated: No.
- Committed: Yes.

**`.code-review-graph/`:**
- Purpose: MCP code-review graph DB (tooling artifact).
- Committed: partially (has `.gitignore`).

---

*Structure analysis: 2026-07-16*
