# Implementation Checklist

Track progress as you build out the security RAG system.

## Phase 1: Corpus & dlt Ingestion (Week 1-2)

- [ ] Set up dlt: `dlt init ai_security_rag postgres`
- [ ] Implement dlt_sources/owasp_llm.py
- [ ] Implement dlt_sources/owasp_agentic.py
- [ ] Implement dlt_sources/mcp_spec.py
- [ ] Implement dlt_sources/mcp_security.py
- [ ] Implement dlt_sources/nist_ai_rmf.py
- [ ] Test each source independently
- [ ] Implement chunking logic (chunk.py)
- [ ] Implement embedding logic (embed.py)
- [ ] Complete run_pipeline.py orchestration
- [ ] Test end-to-end: `python ingestion/run_pipeline.py --sources all --clear-qdrant`
- [ ] Verify Qdrant contains 500+ chunks
- [ ] Verify PostgreSQL has dlt lineage tables

**Deliverable:** `python ingestion/run_pipeline.py` runs cleanly, loads chunks into Qdrant

---

## Phase 2: Retrieval Pipeline (Week 2-3)

- [ ] Complete DenseRetriever in retrieval.py
  - [ ] Embed query using text-embedding-3-small
  - [ ] Query Qdrant with cosine similarity
  - [ ] Return top-5 results with scores
- [ ] Implement BM25Retriever in retrieval.py
  - [ ] Use rank-bm25 or Qdrant sparse indices
  - [ ] Return top-5 BM25 results
- [ ] Implement HybridRetriever in retrieval.py
  - [ ] Combine dense + BM25 via RRF fusion
  - [ ] Add cross-encoder reranking
  - [ ] Return top-5 reranked results
- [ ] Complete rewriter.py
  - [ ] Add threat ID mappings
  - [ ] Normalize queries to threat IDs
- [ ] Test all three approaches with sample queries

**Deliverable:** All three retrieval approaches working, ranked by quality

---

## Phase 3: Evaluation (Week 3-4)

- [ ] Implement generate_qa.py
  - [ ] Prompt gpt-4o-mini to generate Q&A pairs
  - [ ] Generate 150-200 pairs
  - [ ] Save to evaluation/ground_truth.csv
- [ ] Implement eval_retrieval.py
  - [ ] Calculate hit rate for each approach
  - [ ] Calculate MRR for each approach
  - [ ] Calculate Precision@5 for each approach
  - [ ] Save results to evaluation/results/retrieval_eval.json
- [ ] Implement eval_llm.py
  - [ ] Generate answers with Base prompt
  - [ ] Generate answers with Practitioner prompt
  - [ ] Score both variants with LLM-as-judge
  - [ ] Save results to evaluation/results/llm_eval.csv

**Deliverable:** Evaluation reports showing retrieval and LLM quality metrics

---

## Phase 4: LLM Generation (Week 4-5)

- [ ] Complete generator.py
  - [ ] Implement Base prompt variant
  - [ ] Implement Practitioner prompt variant
  - [ ] Add streaming support
- [ ] Test both prompt variants
- [ ] Verify gpt-4o-mini costs are reasonable

**Deliverable:** Both prompt variants working with streaming

---

## Phase 5: API & Streaming (Week 5)

- [ ] Complete api/main.py
  - [ ] Implement POST /query endpoint
  - [ ] Add streaming response support
  - [ ] Implement POST /feedback endpoint
  - [ ] Implement GET /health endpoint
  - [ ] Implement GET /metrics endpoint
- [ ] Test streaming with curl
- [ ] Test with multiple concurrent requests

**Deliverable:** FastAPI server running, /query endpoint streaming responses

---

## Phase 6: Streamlit UI (Week 5-6)

- [ ] Complete ui/app.py
  - [ ] Query input box
  - [ ] Prompt variant selector
  - [ ] Display streaming responses
  - [ ] Add feedback buttons (thumbs-up/-down)
- [ ] Test all UI interactions
- [ ] Verify API integration works

**Deliverable:** Streamlit UI running, accepts queries, shows responses

---

## Phase 7: Monitoring & Logging (Week 6)

- [ ] Complete monitoring/logging.py
  - [ ] Create PostgreSQL schema for query logs
  - [ ] Log all query metadata
  - [ ] Log user feedback
- [ ] Complete monitoring/metrics.py
  - [ ] Define Prometheus metrics
  - [ ] Instrument API endpoints
- [ ] Test query logging: `SELECT COUNT(*) FROM queries;`

**Deliverable:** Queries logged to PostgreSQL, metrics exported

---

## Phase 8: Grafana Dashboard (Week 6-7)

- [ ] Create Grafana datasource (PostgreSQL)
- [ ] Create dashboard with 6 charts:
  - [ ] Query Volume Over Time
  - [ ] Retrieval Latency by Approach
  - [ ] User Feedback Rate
  - [ ] Top 10 Threat IDs
  - [ ] Retrieval Score Distribution
  - [ ] LLM Eval by Prompt Variant
- [ ] Test dashboard with real queries
- [ ] Verify auto-refresh works

**Deliverable:** Grafana dashboard live at http://localhost:3000

---

## Phase 9: Docker & Integration (Week 7)

- [ ] Verify Dockerfile builds
- [ ] Test docker-compose.yml
  - [ ] All 4 services start cleanly
  - [ ] Services can communicate
  - [ ] Health checks pass
- [ ] End-to-end test: Query → API → Streamlit → Monitoring
- [ ] Document any port conflicts or issues

**Deliverable:** `docker-compose up -d` starts full system

---

## Phase 10: Documentation & Cleanup (Week 7-8)

- [ ] Complete README.md
- [ ] Add code comments and docstrings
- [ ] Create IMPLEMENTATION_CHECKLIST.md (this file)
- [ ] Test fresh setup: delete data, docker volumes, re-run
- [ ] Verify requirements.txt has all dependencies
- [ ] Clean up debug prints and logs

**Deliverable:** Clean, documented codebase ready for submission

---

## Phase 11: Evaluation & Testing (Week 8)

- [ ] Run full evaluation:
  - [ ] Generate 200 Q&A pairs
  - [ ] Evaluate all 3 retrieval approaches
  - [ ] Evaluate LLM variants (Base vs Practitioner)
  - [ ] Document results
- [ ] Manual testing of edge cases
- [ ] Performance testing (latency, throughput)

**Deliverable:** Evaluation report with metrics for each rubric item

---

## Phase 12: Peer Review Preparation (Week 8)

- [ ] Select 3 projects from 2025 cohort to review
- [ ] Write detailed feedback for each (>300 words each)
  - [ ] What works well
  - [ ] What could be improved
  - [ ] Specific technical feedback
- [ ] Prepare final submission package

**Deliverable:** 3 peer reviews + polished project repo

---

## 🎯 Success Criteria Checklist

- [ ] All 7 sources ingested (500+ chunks)
- [ ] Retrieval: 3 approaches working, evaluated
- [ ] LLM: 2 prompt variants working, scored by LLM-as-judge
- [ ] API: /query, /feedback, /metrics endpoints functional
- [ ] UI: Streamlit app running, accepts queries
- [ ] Monitoring: 6 Grafana charts configured
- [ ] Docker: Full system runs via docker-compose
- [ ] Evaluation: Hit rate >85%, MRR >0.7, LLM scores >4.0
- [ ] Documentation: README complete with setup, architecture, examples
- [ ] Rubric: 22-25 points expected

---

**Start with Phase 1. Update this checklist as you progress.**
