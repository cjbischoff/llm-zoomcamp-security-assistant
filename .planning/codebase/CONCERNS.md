# Codebase Concerns

**Analysis Date:** 2026-07-16

> This project is an early-stage scaffold. Most modules define the correct
> interfaces but return hardcoded placeholder data. The system will start and
> respond to requests, but does not actually perform retrieval, persistence, or
> monitoring end to end. The dominant concern is **stubs presented as working
> features**, not classic tech debt.

## Tech Debt

**RAG pipeline never retrieves context (core feature stubbed):**
- Issue: `RAGPipeline.stream_answer` hardcodes `retrieval_results = []` and never embeds the query or calls the retriever. Every answer is generated from `"No relevant documents found."`
- Files: `rag/pipeline.py:37-44`
- Impact: The product's primary function (grounded answers) does not work. The LLM answers from parametric memory only — no RAG.
- Fix approach: Instantiate an `Embedder`, embed `rewritten_query`, call `self.retriever.retrieve(query_embedding, query_text)`, build context from real results.

**BM25 / hybrid retrieval is a no-op:**
- Issue: `BM25Retriever.retrieve` returns `[]`; `HybridRetriever.retrieve` ignores BM25 and RRF fusion and just returns dense results. Class docstrings claim "RRF fusion and cross-encoder reranking" that does not exist.
- Files: `rag/retrieval.py:44-48`, `rag/retrieval.py:59-68`
- Impact: "Hybrid search" is dense-only. `rank-bm25` dependency is unused. Reranking absent.
- Fix approach: Implement BM25 (via `rank-bm25` or Qdrant sparse vectors), implement RRF fusion, add cross-encoder rerank or remove the claims.

**Query logging does not persist:**
- Issue: `QueryLogger._init_tables`, `log_query`, and `log_feedback` only emit `logger.info` — nothing writes to Postgres despite `POSTGRES_URL` being read.
- Files: `monitoring/logging.py:20-55`
- Impact: No query history, no feedback storage, Grafana dashboard has no data source rows to render.
- Fix approach: Create tables via SQLAlchemy (already a dependency) and execute inserts.

**Metrics are hardcoded zeros:**
- Issue: `MetricsCollector.get_metrics` returns a static dict of zeros/empties. The `/metrics` endpoint reports nothing real. Prometheus counters in `monitoring/metrics.py` are defined but never incremented anywhere.
- Files: `monitoring/logging.py:58-69`, `monitoring/metrics.py` (counters never `.inc()`'d)
- Impact: Observability is cosmetic; dashboards will be empty.
- Fix approach: Wire the pipeline to increment the Prometheus metrics and query Postgres for aggregates.

**Q&A generation stubbed:**
- Issue: `generate_qa_pair` returns templated fake strings instead of calling the model.
- Files: `rag/generator.py:67-74`, `evaluation/eval_llm.py:52`, `evaluation/eval_retrieval.py:55`
- Impact: Evaluation harness produces meaningless results.
- Fix approach: Implement the LLM call; wire eval scripts to a real dataset.

**UI does not call the API:**
- Issue: `ui/app.py` defines an unused async `query_api()` and then renders a static placeholder answer. Feedback buttons only show toasts; they never POST to `/feedback`.
- Files: `ui/app.py:65-96`, `ui/app.py:104-116`
- Impact: The Streamlit UI is a mockup, not a client.
- Fix approach: Actually invoke `query_api()` and stream `response`; POST feedback with the returned query id.

## Known Bugs

**`/metrics` endpoint raises ImportError (broken import):**
- Symptoms: `GET /metrics` returns 500. `api/main.py` does `from monitoring.metrics import MetricsCollector`, but `MetricsCollector` is defined in `monitoring/logging.py`, not `monitoring/metrics.py`.
- Files: `api/main.py:101`, `monitoring/metrics.py` (no such class), `monitoring/logging.py:58`
- Trigger: Any request to `/metrics`.
- Workaround: Import from `monitoring.logging` instead, or move the class.

**Health check always reports healthy:**
- Symptoms: `/health` returns `qdrant/postgres/openai` all connected regardless of actual state.
- Files: `api/main.py:37-47`
- Trigger: Always. Dependencies could be down and the check still passes.
- Workaround: Perform real connectivity pings before reporting status.

**`/feedback` signature will misbehave as documented:**
- Symptoms: `feedback_endpoint(query_id: str, feedback: int)` uses bare params, so FastAPI treats them as query parameters, not a JSON body. The UI (if wired) sends neither.
- Files: `api/main.py:79-94`
- Fix approach: Define a Pydantic request model.

## Security Considerations

**Default/committed credentials in compose and env example:**
- Risk: `docker-compose.yml` hardcodes `POSTGRES_PASSWORD: password` and Grafana `admin/admin`. `.env.example` ships `password` and `POSTGRES_URL` with inline creds.
- Files: `docker-compose.yml` (postgres env, grafana env), `.env.example`
- Current mitigation: None; these are placeholders but invite copy-paste into production.
- Recommendations: Use secrets/`.env` for real deploys, force Grafana password change, never reuse `password`.

**No input validation, rate limiting, or auth on the API:**
- Risk: `/query` forwards arbitrary user text straight into an LLM prompt with no length cap, no auth, no rate limit. Prompt-injection and cost-abuse exposure. `user_id` is unauthenticated free text.
- Files: `api/main.py:24-76`, `rag/generator.py:27-58`
- Current mitigation: `max_tokens=500` caps output only.
- Recommendations: Add auth, per-user rate limiting, input length validation, and prompt-injection guardrails (see OWASP LLM01 — which this app is literally about).

**Error detail leaked to clients:**
- Risk: `HTTPException(status_code=500, detail=str(e))` returns raw exception text; the generator yields `f"Error generating answer: {str(e)}"` into the stream.
- Files: `api/main.py:76`, `api/main.py:94`, `rag/generator.py:64-65`
- Recommendations: Log full error server-side, return generic message to client.

**Postgres and Qdrant ports published to host with weak/no auth:**
- Risk: `docker-compose.yml` maps `5432` and `6333` to the host; Postgres uses `password`, Qdrant has no auth.
- Files: `docker-compose.yml` (ports sections)
- Recommendations: Bind to internal network only unless external access is required.

## Performance Bottlenecks

**Embeddings and retrieval are synchronous inside an async pipeline:**
- Problem: `Embedder` and the Qdrant `DenseRetriever` use synchronous clients. Once wired in, they will block the FastAPI event loop per request.
- Files: `ingestion/transforms/embed.py:25-30`, `rag/retrieval.py:22-26`
- Cause: sync SDK calls in an `async def` path.
- Improvement path: Run blocking calls in a threadpool (`asyncio.to_thread`) or use async clients.

**New pipeline object per request:**
- Problem: `query_endpoint` constructs a fresh `RAGPipeline()` (and thus new OpenAI/Qdrant clients) on every request.
- Files: `api/main.py:61`
- Improvement path: Instantiate once at startup (dependency/singleton).

## Fragile Areas

**Silent failures via broad `except` returning empty:**
- Files: `rag/retrieval.py:36-38` (dense retrieval), `rag/generator.py:64-65`
- Why fragile: A Qdrant outage yields `[]` and a confident empty-context answer with no signal to the caller. Errors are printed, not surfaced.
- Safe modification: Distinguish "no results" from "backend down"; propagate/log with structured errors.
- Test coverage: None (no tests exist in the repo).

**Threat-ID rewriter matches on naive substring:**
- Files: `rag/rewriter.py:37-52`
- Why fragile: First-match-wins substring scan over an unordered dict; overlapping patterns (e.g. "supply chain") can misclassify, and dict ordering determines the result.
- Safe modification: Use word-boundary regex and define precedence explicitly.

## Scaling Limits

**Single-process, in-memory, no persistence layer wired:**
- Current capacity: Effectively demo-only. No connection pooling, no persistence, one uvicorn worker with `reload=True` in `__main__`.
- Limit: Any real concurrency will contend on the event loop (sync clients) and lose all logs (nothing persisted).
- Scaling path: Persist to Postgres, pool connections, disable `reload` in prod, run multiple workers behind a proxy.

## Dependencies at Risk

**Pinned versions appear incorrect / non-existent (verify before install):**
- Risk: `qdrant-client==2.7.0` does not correspond to a real 2.x release line (client is 1.x); `sentence-transformers==2.2.2` is old and has known install issues with recent `huggingface_hub`; `openai==1.6.1` is far behind the SDK used by the code style. Low-confidence — needs `pip install` verification.
- Files: `requirements.txt`
- Impact: `docker build` / `pip install` may fail or resolve unexpected versions.
- Migration plan: Verify each pin against the registry and the API actually called in code; bump to known-good versions.

**Unused dependencies:**
- Risk: `rank-bm25`, `scikit-learn`, `PyPDF2`, `markdownify`, `sentence-transformers` are declared but BM25/rerank/eval logic is stubbed. `numpy` imported in `rag/retrieval.py` but unused.
- Files: `requirements.txt`, `rag/retrieval.py:7`
- Impact: Bloated image, unclear which deps are load-bearing.
- Migration plan: Remove or wire up as features land.

## Missing Critical Features

**No tests exist:**
- Problem: Zero test files in the repo despite `httpx`, `scikit-learn` present and an `evaluation/` package.
- Blocks: Safe refactoring; verifying that stubs get replaced with real behavior.

**Ingestion → embed → Qdrant upsert not connected:**
- Problem: `Embedder` produces vectors but no code upserts them into the Qdrant `security_rag` collection, and no collection creation is shown. Retrieval therefore has nothing to search.
- Files: `ingestion/run_pipeline.py`, `ingestion/transforms/embed.py`, `rag/retrieval.py`
- Blocks: The entire retrieval path — even once wired, the collection is empty.

## Test Coverage Gaps

**Everything (100% untested):**
- What's not tested: RAG pipeline, retrieval, generator, API endpoints, logging, ingestion, rewriter.
- Files: entire `rag/`, `api/`, `monitoring/`, `ingestion/`, `evaluation/` trees.
- Risk: Stubs can be swapped for real logic with no safety net; regressions invisible.
- Priority: High — start with `rewriter` (pure logic, easy) and API contract tests.

---

*Concerns audit: 2026-07-16*
