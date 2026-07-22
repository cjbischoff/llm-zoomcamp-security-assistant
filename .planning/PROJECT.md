# Security RAG Assistant (LLM Zoomcamp 2026 Capstone)

## What This Is

A retrieval-augmented generation assistant that answers AI/LLM security questions grounded in authoritative sources (OWASP LLM Top 10, OWASP Agentic Top 10, MCP protocol spec, MCP security docs, NIST AI RMF). For security engineers and practitioners who need cited, framework-anchored answers about LLM/agent threats and mitigations. Built as the LLM Zoomcamp 2026 capstone submission.

## Core Value

Ask a security question, get an accurate answer grounded in real retrieved source passages (not the model's parametric memory) with threat IDs and citations. If retrieval doesn't actually work end-to-end, nothing else matters.

## Requirements

### Validated

<!-- Scaffold exists; these are structural, not shipped-and-proven. -->

- ✓ Project scaffold + layered architecture (ingestion / rag / api / ui / monitoring / evaluation) — existing
- ✓ Threat-ID mapping dictionary (OWASP/MCP/NIST canonical IDs) — existing
- ✓ dlt source definitions for 5 corpora + docker-compose (Qdrant/Postgres/Grafana) — existing (unwired)
- ✓ **Real ingestion (Phase 1):** dlt → Postgres staging → chunk → 1536-dim OpenAI embed → idempotent Qdrant upsert. `python ingestion/run_pipeline.py` populates **850 points** across all **5 distinct sources** (owasp_llm_top_10, owasp_agentic_top_10, mcp_protocol_spec, mcp_security_docs, nist_ai_rmf) at size=1536/cosine; re-run leaves the count unchanged (content-hash uuid5 IDs). REP-01 pins corrected; 20 pytest tests green.
- ✓ **Real retrieval + grounded generation (Phase 2):** dense `query_points` search over the 850-point collection → 0.4 cosine refuse-gate (off-topic/below-floor → "not in the indexed sources", LLM not called) → streamed `gpt-4o-mini` answers with inline `[threat-ID]` citations + Sources block. Two prompt variants (Practitioner default, Base via `prompt_variant`); RET-02 distinguishes backend-down / collection-missing / empty (no silent `[]`). Verified live: real `[LLM01]` grounded answer, off-topic refusal, 395-chunk incremental HTTP stream; 31 pytest tests green.
- ✓ **Hybrid search + reranking + query rewriting (Phase 3):** `retrieval_mode` (dense | hybrid | hybrid_rerank) threaded through `RAGPipeline` + `/query` (enum-validated). Hybrid = dense + rank-bm25 sparse leg + manual RRF fusion (k=60) on Qdrant point id + detected-threat-id soft-boost (RET-03/RET-04); cross-encoder Reranker over the fused top-20 → top-5, run off the event loop via `asyncio.to_thread` (BON-01/BON-03). Rewriter rebuilt to the verified OWASP taxonomy (LLM01–10 + ASI01–10), word-boundary + longest-match, returning `(query, id|None)` (BON-02). **Provable, not claimed:** live probes GREEN against the real 850-doc collection — hybrid top-5 ≠ dense top-5, and the real cross-encoder reorders the fused set; full suite 54 passed / 3 skipped (skips only offline).
- ✓ **Ground-truth evaluation harness (Phase 4):** 78 real Q&A pairs generated from the live corpus (chunk_id = real uuid5 point id), one CSV reused by both eval lines (EVL-01). Retrieval metrics (hit-rate/MRR/precision@5) computed on real data across all 3 modes — **hybrid_rerank wins** (84.62% hit / 0.773 MRR) and is now the **production default** `retrieval_mode` (EVL-02, D-08). gpt-4o LLM-as-judge (distinct from the gpt-4o-mini generator) scores both prompt variants on accuracy/completeness/hallucination-groundedness, with a 5-pair human spot-check mitigating circularity (EVL-03). Grader-readable `evaluation/EVALUATION.md` committed (EVL-04). Live run done + committed; full suite 67 passed / 0 skipped with a key.
- ✓ **Interface wiring + monitoring persistence (Phase 5):** FastAPI `lifespan` builds Qdrant client + `AsyncOpenAI` + embedder + SQLAlchemy engine once on `app.state`, injected per-request into `RAGPipeline` (additive injection keeps Phase 2/3/4 tests green) — INT-01. `/feedback` (Pydantic `rating: Literal[-1,1]`) + `/query` persist to Postgres `query_log`/`feedback_log` via SQLAlchemy Core parameterized inserts off-loop (`asyncio.to_thread`); `query_id` rides an `X-Query-Id` header to tie feedback to its query (INT-02/MON-01). `/metrics` exposes real Prometheus counters (`generate_latest`), `/health` 503s on a downed dep (INT-03/MON-02). Streamlit UI streams the grounded answer, shows citations, feedback thumbs persist on 2xx, and fails visibly when the API is down (INT-04). Grafana renders 6 non-zero Postgres SQL panels after a seed batch (MON-03). **Verified live via a driven browser (agent-browser):** streaming answer + `[LLM01]` citation, feedback persisted (row +1), API-down red error with no stale content, and 6 Grafana panels rendering — after fixing 5 real defects (Grafana datasource provisioning schema + dashboard datasource type; Streamlit 1.28.1 API compatibility). Full suite 79 passed / 1 skipped.

- ✓ **Containerization + reproducibility + docs (Phase 6):** dependency pins reconciled to verified-working versions (streamlit 1.56, httpx 0.28.1, scikit-learn 1.9, numpy 2.4.6) with a committed `requirements.lock`; Dockerfile installs from the lock. `docker-compose up` brings up all 6 services (postgres/qdrant/**ingest**/app/ui/grafana) with a one-shot idempotent `ingest` init (short-circuits on the populated 850-pt collection) as the readiness gate — the never-passable qdrant curl healthcheck removed (REP-02). **Verified end-to-end on the real compose stack:** app `/health` 200 all-connected, containerized `POST /query` returns a grounded answer + `X-Query-Id`, no manual post-start steps. Grader-honest README (real 5 sources, setup/ingest/serve/evaluate, org cloud-hosting tradeoff, grep-matched bonuses, no secrets) + stale scaffold docs deleted (REP-03); `test_readme_honesty.py` enforces it. Bare offline `pytest` exits 0 (72 passed / 12 skipped); full suite with infra 84 passed / 0 failed (REP-04).

### Active

<!-- Milestone v1.0 complete — all requirements validated. -->

- (none — v1.0 shipped)

### Out of Scope

- Cloud / public hosting (AWS, GCP, Vercel, Heroku, etc.) — org policy forbids hosting internal/AI tools on personal or public services; local-docker only. (Forgoes any cloud-deploy rubric points by design.)
- Auth / rate limiting / prod-grade prompt-injection guardrails — capstone is a demo, not production; note the irony (app is about LLM01) but not in scope for the rubric.
- Real-time corpus updates / scheduled re-ingestion — manual ingest is sufficient for submission.
- Multi-user accounts, session history UI — single-user demo.

## Context

- **Grading target:** LLM Zoomcamp 2026 capstone rubric, aiming 22-25 points. Rubric: knowledge base, retrieval pipeline (multiple approaches), evaluation (retrieval + LLM), interface, monitoring+feedback, automated ingestion (dlt = +2), Docker (+1), bonuses (hybrid/rerank/rewriting), documentation.
- **Current state:** **Milestone v1.0 COMPLETE — all 6 phases done, all requirements validated.** The full Security RAG system builds and runs from a clean `docker-compose up` (6 services, auto-ingest gate, no manual steps), is queryable end-to-end with grounded `[threat-ID]`-cited streamed answers across dense/hybrid/hybrid_rerank retrieval (eval-winner `hybrid_rerank` is the prod default), scores itself against a real ground-truth harness (committed `evaluation/EVALUATION.md`), persists query/feedback to Postgres with a live Grafana dashboard + Prometheus `/metrics`, serves a real-streaming Streamlit UI, and ships a grader-honest README + `requirements.lock`. Verified live end-to-end (containerized stack + driven-browser UI/Grafana; 84 pytest tests green with infra, offline bare `pytest` exits 0). Ready for `/gsd-ship`.
- **Dep pins:** Fixed in Phase 1 (REP-01) — `qdrant-client` 1.x, `pypdf` (replaced non-existent `PyPDF2==4.0.1`), `tiktoken` added; `uv pip compile` resolves 121 packages on Python 3.11.
- **Rubric/plan references:** `/Users/christopher/Workspace/topic_zoomcamp-llm/synthesis/` (capstone plan + implementation guide); course rubric at github.com/DataTalksClub/llm-zoomcamp/blob/main/project.md.

## Constraints

- **Tech stack (locked)**: Qdrant (vectors), OpenAI API gpt-4o / gpt-4o-mini, dlt (ingestion), 5 security sources — do not swap.
- **Deployment**: Local Docker only — no external hosting (org policy).
- **Timeline**: Submission by end of LLM Zoomcamp 2026 cohort (late July / early August 2026).
- **Testing**: Pragmatic — tests on load-bearing logic, not exhaustive coverage; fit the deadline.
- **Embedding**: OpenAI `text-embedding-3-small`; embedding dimension must match between ingest and Qdrant collection.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Finish scaffold rather than rewrite | Structure is sound; stubs need real impl, not redesign | ✓ Validated (Phase 1 — ingestion shipped by extending stubs) |
| OWASP Agentic ingested from OWASP crosswalk repo (ASI01–ASI10) | Primary Top-10 doc is a gated PDF; the GenAI Data Security Initiative crosswalk repo is the authoritative *fetchable* form | ✓ Phase 1 (rewriter THREAT_MAPPINGS→ASI remap deferred to Phase 3) |
| Implement all 3 bonuses (hybrid+rerank, rewriting, doc rerank) | Needed to reach 22-25 pt target | — Pending |
| Keep both FastAPI + Streamlit, wire them | Rubric interface item; Streamlit calls API for real | — Pending |
| Pragmatic tests, not full TDD | Rubric doesn't grade tests; deadline pressure | — Pending |
| Local-docker only, no cloud deploy | Org policy forbids public/personal hosting | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-21 after Phase 6 completion — Milestone v1.0 COMPLETE (all 6 phases shipped)*
