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

### Active

<!-- Hypotheses until shipped and validated. All currently stubbed. -->

- [ ] Real ingestion: fetch 5 sources → chunk → embed → upsert into Qdrant (dlt-orchestrated, idempotent)
- [ ] Real retrieval: dense vector search against populated Qdrant collection
- [ ] Real generation: OpenAI streaming answers grounded in retrieved context, base + practitioner prompt variants
- [ ] Bonus — hybrid search: dense + BM25 + RRF fusion
- [ ] Bonus — cross-encoder reranking on fused results
- [ ] Bonus — query rewriting: free text → canonical threat IDs (word-boundary, precedence-safe)
- [ ] Evaluation: retrieval metrics (hit rate, MRR, precision@5) + LLM-as-judge over a real ground-truth Q&A set
- [ ] Monitoring: persist queries/feedback to Postgres, increment Prometheus metrics, populate Grafana dashboard
- [ ] Interfaces wired: FastAPI backend serving real pipeline; Streamlit UI calls the API and streams responses; feedback POSTs persist
- [ ] Pragmatic tests on load-bearing logic (rewriter, retrieval, eval, API contract)
- [ ] Reproducible run: `docker-compose up` + documented ingest/serve steps produce a working system from scratch

### Out of Scope

- Cloud / public hosting (AWS, GCP, Vercel, Heroku, etc.) — org policy forbids hosting internal/AI tools on personal or public services; local-docker only. (Forgoes any cloud-deploy rubric points by design.)
- Auth / rate limiting / prod-grade prompt-injection guardrails — capstone is a demo, not production; note the irony (app is about LLM01) but not in scope for the rubric.
- Real-time corpus updates / scheduled re-ingestion — manual ingest is sufficient for submission.
- Multi-user accounts, session history UI — single-user demo.

## Context

- **Grading target:** LLM Zoomcamp 2026 capstone rubric, aiming 22-25 points. Rubric: knowledge base, retrieval pipeline (multiple approaches), evaluation (retrieval + LLM), interface, monitoring+feedback, automated ingestion (dlt = +2), Docker (+1), bonuses (hybrid/rerank/rewriting), documentation.
- **Current state:** 73-file scaffold. Correct interfaces, but nearly every module returns hardcoded placeholder data — RAG never retrieves, logging/metrics don't persist, `/metrics` import is broken, UI is a mockup, zero tests. See `.planning/codebase/CONCERNS.md`.
- **Known dep risk:** `requirements.txt` pins appear wrong (`qdrant-client==2.7.0` non-existent, `openai==1.6.1` stale, several unused deps). Verify/bump before relying on them.
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
| Finish scaffold rather than rewrite | Structure is sound; stubs need real impl, not redesign | — Pending |
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
*Last updated: 2026-07-15 after initialization*
