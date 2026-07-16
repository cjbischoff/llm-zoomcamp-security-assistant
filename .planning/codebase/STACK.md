# Technology Stack

**Analysis Date:** 2026-07-16

## Languages

**Primary:**
- Python 3.11 - All application code (`api/`, `rag/`, `ingestion/`, `evaluation/`, `monitoring/`, `ui/`)

**Secondary:**
- SQL (PostgreSQL dialect) - Query logging, dlt destination
- JSON/YAML - Grafana provisioning (`monitoring/grafana/provisioning/`)

## Runtime

**Environment:**
- Python 3.11 (`python:3.11-slim` base image in `Dockerfile`)

**Package Manager:**
- pip
- Lockfile: missing (pinned versions in `requirements.txt`, no `requirements.lock`/`uv.lock`)

## Frameworks

**Core:**
- FastAPI 0.109.0 - HTTP API (`api/main.py`), served by uvicorn
- Streamlit 1.28.1 - User-facing chat UI (`ui/app.py`)
- dlt 0.5.0 `[postgres,requests,connectors]` - Orchestrated ingestion pipeline (`ingestion/run_pipeline.py`)

**Testing / Evaluation:**
- scikit-learn 1.3.2 - Retrieval/eval metrics (`evaluation/`)
- No dedicated test framework detected (no pytest/jest in `requirements.txt`)

**Build/Dev:**
- uvicorn[standard] 0.27.0 - ASGI server (container `CMD`)
- Docker / docker-compose 3.8 - Local orchestration (`docker-compose.yml`)

## Key Dependencies

**Critical:**
- openai 1.6.1 - LLM generation (`gpt-4o-mini`) and embeddings (`text-embedding-3-small`, 512-dim); see `rag/generator.py`, `ingestion/transforms/embed.py`
- qdrant-client 2.7.0 - Vector search (`rag/retrieval.py`)
- sentence-transformers 2.2.2 - Local embedding / reranking models
- rank-bm25 0.2.2 - BM25 sparse retrieval (`rag/retrieval.py`)
- pydantic 2.5.0 / pydantic-settings 2.1.0 - Config and request/response models

**Data processing:**
- pandas 2.1.4, numpy 1.24.3
- PyPDF2 4.0.1 - NIST AI RMF PDF parsing (`ingestion/dlt_sources/nist_ai_rmf.py`)
- beautifulsoup4 4.12.2, markdownify 0.11.6 - HTML → markdown
- requests 2.31.0, httpx 0.25.2 - HTTP clients

**Infrastructure:**
- psycopg2-binary 2.9.9, SQLAlchemy 2.0.23 - PostgreSQL access / query logging (`monitoring/logging.py`)
- prometheus-client 0.19.0 - Metrics (`monitoring/metrics.py`)
- python-dotenv 1.0.1 - `.env` loading

## Configuration

**Environment:**
- `.env` file (template: `.env.example`) loaded via python-dotenv
- Key configs: `OPENAI_API_KEY`, `POSTGRES_URL` / `DLT_POSTGRES_*`, `QDRANT_HOST`/`QDRANT_PORT`/`QDRANT_COLLECTION_NAME`, `API_HOST`/`API_PORT`, `STREAMLIT_PORT`, `ENVIRONMENT`, `LOG_LEVEL`
- Config read directly via `os.getenv()` in modules; pydantic-settings available but wiring not centralized

**Build:**
- `Dockerfile` - installs system deps (git, curl, build-essential, postgresql-client) then `requirements.txt`
- `docker-compose.yml` - services: postgres (15-alpine), qdrant (latest), grafana (latest), app

## Platform Requirements

**Development:**
- Docker + docker-compose, or local Python 3.11 with running Postgres and Qdrant

**Production:**
- Container image exposes ports 8000 (FastAPI) and 8501 (Streamlit); default `CMD` runs the API only

---

*Stack analysis: 2026-07-16*
