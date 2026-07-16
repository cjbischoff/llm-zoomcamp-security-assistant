# External Integrations

**Analysis Date:** 2026-07-16

## APIs & External Services

**LLM / Embeddings:**
- OpenAI - Answer generation and embeddings
  - SDK/Client: `openai` 1.6.1 (`AsyncOpenAI` in `rag/generator.py`, sync client in `ingestion/transforms/embed.py`)
  - Models: `gpt-4o-mini` (generation), `text-embedding-3-small` (512-dim embeddings)
  - Auth: `OPENAI_API_KEY`

**Ingestion Sources (dlt, `ingestion/dlt_sources/`):**
- OWASP Top 10 for LLM - `https://github.com/OWASP/Top-10-for-LLM` (`owasp_llm.py`)
- OWASP Agentic Top 10 - `https://github.com/OWASP/www-project-agentic-top-10` (`owasp_agentic.py`)
- NIST AI RMF - `https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf` (`nist_ai_rmf.py`, PDF via PyPDF2)
- MCP Spec - `https://github.com/modelcontextprotocol/spec` (`mcp_spec.py`)
- MCP Security Best Practices - `https://modelcontextprotocol.io/specification/draft/basic/security_best_practices` (`mcp_security.py`)

## Data Storage

**Databases:**
- PostgreSQL 15 - dlt destination + query logging
  - Connection: `POSTGRES_URL` (SQLAlchemy) / `DLT_POSTGRES_*` (dlt)
  - Client: psycopg2-binary, SQLAlchemy (`monitoring/logging.py`)
- Qdrant (latest) - Vector store for dense retrieval
  - Connection: `QDRANT_HOST`, `QDRANT_PORT` (6333), `QDRANT_COLLECTION_NAME` (`security_rag`)
  - Client: qdrant-client (`rag/retrieval.py`)

**File Storage:**
- Local filesystem - `./data` (raw ingestion), mounted into app container

**Caching:**
- None detected

## Authentication & Identity

**Auth Provider:**
- None - API endpoints (`api/main.py`) are unauthenticated; only OpenAI API key auth to external service

## Monitoring & Observability

**Metrics:**
- Prometheus - `prometheus-client` counters/histograms/gauges (`monitoring/metrics.py`); exposed at `GET /metrics`

**Dashboards:**
- Grafana (latest) - provisioned via `monitoring/grafana/provisioning/` (postgres datasource, `security_rag_dashboard.json`)

**Error Tracking:**
- None - errors printed/logged locally (stdlib `logging`, `print`)

**Logs:**
- Query logging to PostgreSQL (`monitoring/logging.py`, `QueryLogger`) — table init is currently a placeholder

## CI/CD & Deployment

**Hosting:**
- Docker Compose (local); no cloud deploy config detected

**CI Pipeline:**
- None detected (no `.github/workflows`, CI config)

## Environment Configuration

**Required env vars:**
- `OPENAI_API_KEY`
- `POSTGRES_URL` / `DLT_POSTGRES_USER|PASSWORD|HOST|PORT|DATABASE`
- `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_COLLECTION_NAME`

**Secrets location:**
- `.env` file (template `.env.example`); compose passes `OPENAI_API_KEY` through from host env. Postgres/Grafana use hardcoded default credentials in `docker-compose.yml` (dev only).

## Webhooks & Callbacks

**Incoming:**
- HTTP endpoints (`api/main.py`): `GET /health`, `POST /query`, `POST /feedback`, `GET /metrics`

**Outgoing:**
- None

---

*Integration audit: 2026-07-16*
