# Security RAG Assistant

*LLM Zoomcamp 2026 capstone*

A retrieval-augmented generation assistant that answers AI/LLM security questions
grounded in authoritative sources. Ask a security question and get an answer built
from real retrieved source passages — not the model's parametric memory — with
threat IDs and citations. If retrieval returns nothing relevant, the assistant
refuses ("not in the indexed sources") rather than guessing. The corpus is five
authoritative security frameworks (OWASP LLM Top 10, OWASP Agentic Top 10, the MCP
protocol spec, MCP security docs, and the NIST AI RMF), embedded into a 850-point
Qdrant collection.

## Architecture

Offline ingestion builds the vector corpus; the online serving path answers queries
against it.

```
docker compose up
        │
        ├── postgres  (:5432)  dlt state + query/feedback logs
        ├── qdrant    (:6333)  vector store (850 points, 1536-dim, cosine)
        ├── grafana   (:3000)  6 SQL dashboard panels over postgres
        ├── ingest    (one-shot) dlt fetch → chunk → embed → idempotent Qdrant upsert
        ├── app       (:8000)  FastAPI: /query (streaming), /feedback, /health, /metrics
        └── ui        (:8501)  Streamlit chat that calls the API
```

`ingest` is a one-shot gate: `app` and `ui` wait for it to complete, and it
short-circuits (no duplicate upserts) on repeat runs because point IDs are content-hash
`uuid5`s.

The query path is: rewrite → retrieve → 0.4 cosine refuse-gate → stream a
`gpt-4o-mini` answer with inline `[threat-ID]` citations. Retrieval offers three modes:

- **dense** — cosine vector search (baseline)
- **hybrid** — dense + BM25 sparse leg fused with Reciprocal Rank Fusion (k=60)
- **hybrid_rerank** — hybrid, then a cross-encoder reranks the fused top-20 to top-5

`hybrid_rerank` is the evaluation-winning production default (see
[evaluation/EVALUATION.md](evaluation/EVALUATION.md)).

## Data sources

The corpus is exactly these five, named as they appear in the ingestion registry and
the evaluation set:

| Source | Contributes |
|--------|-------------|
| `owasp_llm_top_10` | LLM01–LLM10 threats and mitigations for LLM applications |
| `owasp_agentic_top_10` | ASI01–ASI10 threats adapted for agentic systems |
| `mcp_protocol_spec` | Model Context Protocol architecture and capabilities |
| `mcp_security_docs` | MCP threat modeling and security best practices |
| `nist_ai_rmf` | NIST AI Risk Management Framework functions and controls |

## Quickstart (Docker)

```bash
git clone <this-repo> && cd llm-zoomcamp-security-assistant
cp .env.example .env
# edit .env and set OPENAI_API_KEY to your key
docker compose up        # docker-compose up also works
```

Ingestion runs automatically on the first `up` and short-circuits on repeat — there is
no manual ingest step. Once the stack is healthy:

- API: http://localhost:8000
- UI: http://localhost:8501
- Grafana: http://localhost:3000 (admin/admin — local demo only)
- Qdrant: http://localhost:6333

## Manual / local run (no Docker)

You still need Postgres and Qdrant reachable (the Docker services, or your own). Then:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock
python ingestion/run_pipeline.py            # populate Qdrant (idempotent)
uvicorn api.main:app --host 0.0.0.0 --port 8000
streamlit run ui/app.py                      # in a second shell
python -m evaluation.run_eval               # optional: reproduce the eval
```

## Evaluation

Retrieval quality (hit-rate, MRR, precision@5) is measured across all three modes on a
78-pair, non-circular ground-truth set built from real Qdrant point IDs;
`hybrid_rerank` wins (84.62% hit / 0.773 MRR) and is wired as the production default.
A `gpt-4o` LLM-as-judge (distinct from the `gpt-4o-mini` generator) scores both prompt
variants on accuracy, completeness, and groundedness, backstopped by a human
spot-check. Full methodology and numbers: [evaluation/EVALUATION.md](evaluation/EVALUATION.md).

## Bonuses implemented

Only the bonuses that exist in code are claimed — each traces to a symbol under `rag/`:

- **Hybrid search** — `rrf_fuse` in `rag/retrieval.py` (dense + BM25 via RRF)
- **Cross-encoder reranking** — `Reranker` / `CrossEncoder` in `rag/retrieval.py`
- **Query rewriting** — `QueryRewriter` in `rag/rewriter.py` (free text → canonical threat IDs)

## Tests

```bash
pytest -q
```

Offline, the live-stack tests skip cleanly and the suite exits 0. The live probes
require the stack up and an `OPENAI_API_KEY`. The doc-lint
`tests/test_readme_honesty.py` runs offline and mechanically guards this README:
all five source IDs present, no committed secret key, every claimed bonus grep-matches
`rag/`.

## Tradeoffs and disclosure

- **Local Docker only, by org policy.** Hosting internal/AI tools on personal or public
  cloud (AWS, GCP, Vercel, Heroku, …) is forbidden here, so this deliberately forgoes
  the ~2-point cloud-deploy rubric line.
- **No auth, rate limiting, or prompt-injection guardrails.** This is a demo, not
  production — noted with the irony that the app is itself about LLM01.

## Secrets

No secrets are committed. `.env` is gitignored; `.env.example` is a placeholder-only
template; Docker Compose injects the key at runtime via `env_file`. Never paste a real
key into this repo.
