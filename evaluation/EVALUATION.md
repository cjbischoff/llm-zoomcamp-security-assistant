# Evaluation Report — Security RAG Assistant

Offline evaluation of the Phase 1-3 system (850-doc Qdrant `security_rag`
collection, three retrieval modes, 0.4-gated `gpt-4o-mini` generation with two
prompt variants) against a real, non-circular ground-truth Q&A set. All numbers
below are produced by a live run of `python -m evaluation.run_eval` against the
populated collection — no placeholders.

## Methodology

**Ground truth (EVL-01, D-01/D-02/D-03).** The set is built by scrolling the live
Qdrant collection and seeded-sampling ~6-8 chunks per source across all five
corpora (owasp_llm_top_10, owasp_agentic_top_10, mcp_protocol_spec,
mcp_security_docs, nist_ai_rmf). For each sampled chunk, `gpt-4o-mini` authors a
realistic question + reference answer. Crucially, each row's `chunk_id` is the
REAL `uuid5` Qdrant point id (not an enumeration index) — this is the relevance
label the retrieval join depends on. The committed CSV (`evaluation/ground_truth.csv`) is the
single source of truth for both eval lines.

**Retrieval metrics (EVL-02, D-06/D-07).** For each pair we embed the raw
question once with the production `Embedder` (1536-dim, matching the collection)
and drive all three modes through the real production retrievers. A retrieved
hit counts as relevant iff its point `id` equals the ground-truth `chunk_id`.
The comparison is kept uniform across modes (raw-question embed,
`detected_id=None`) so the differences reflect retrieval quality rather than the
rewriter's soft-boost (research Open Question 2). We report hit-rate, MRR, and
precision@5.

*Precision@5 single-gold bound.* Each question has exactly one gold chunk, so at
most 1 of the top-5 can be relevant: precision@5 ∈ (0, 0.2) per query and its
mean equals `hit_rate / 5` by construction (research Pitfall 2). A value near
~0.16 is therefore expected and reads correctly — it is not a defect. MRR is the
sharper rank-quality signal here.

**LLM-as-judge (EVL-03, D-09/D-10).** For each pair we retrieve the full hits via
the winning mode, reassemble the exact numbered `[threat_id] (source:)` context
block the pipeline builds, generate the production answer for BOTH prompt
variants (`base`, `practitioner`), and score each with a `gpt-4o` judge over the
FULL context (never truncated) using JSON mode. Scores are integers 1-5 on three
dimensions — accuracy, completeness, hallucination (higher = better/more
grounded), temperature 0.

**Circularity mitigation (D-04).** The judge (`gpt-4o`) is a different model from
the generator (`gpt-4o-mini`) — the cross-model half. But the gold reference is
itself `gpt-4o-mini`-authored, so accuracy partly measures model-to-model
agreement; the hallucination dimension is therefore anchored on groundedness in
the RETRIEVED CONTEXT (the least-circular objective signal), and a ~5-pair human
spot-check (below) is the real backstop.

## Ground Truth

- Total pairs: **78**
- CSV path: `evaluation/ground_truth.csv` (committed)
- Per-source counts:

| Source | Pairs |
|--------|-------|
| mcp_protocol_spec | 16 |
| mcp_security_docs | 16 |
| nist_ai_rmf | 16 |
| owasp_agentic_top_10 | 14 |
| owasp_llm_top_10 | 16 |

## Retrieval Metrics

Hit-rate / MRR / precision@5 across the three modes on the ground-truth set:

| Mode | Hit Rate | MRR | Precision@5 |
|------|----------|-----|-------------|
| dense | 82.05% | 0.604 | 0.164 |
| hybrid | 84.62% | 0.702 | 0.169 |
| hybrid_rerank | 84.62% | 0.773 | 0.169 |

## Chosen Production Mode

**Winner: `hybrid_rerank`** (selected by hit-rate, MRR as tie-breaker — D-08).

`hybrid_rerank` adds an ~80MB cross-encoder download and per-query rerank latency on top of hybrid — the metric win must justify that cost.

The winning mode is wired as the production default `retrieval_mode` in both
`rag/pipeline.py` and `api/main.py` (kept in sync — research Pitfall 5), or, if
`dense` wins, the current default stands and that is recorded as the finding
(D-08 explicitly allows this).

## LLM-as-Judge

Mean judge scores (1-5, higher is better) per prompt variant over the winning
mode's retrieved context:

| Variant | Accuracy | Completeness | Hallucination (grounded) |
|---------|----------|--------------|--------------------------|
| base | 4.79 | 4.53 | 4.85 |
| practitioner | 4.56 | 4.37 | 4.56 |

## Human Spot-Check

A ~5-pair human calibration of the judge (the human half of the circularity
mitigation, D-10). A reviewer reads each (question, retrieved context, generated
answer, judge scores) tuple and records agree/disagree per dimension.

Five pairs sampled across sources and both variants (judge scores A = accuracy,
C = completeness, H = hallucination/groundedness, each 1-5):

| # | Question | Variant | Judge (A/C/H) | Human verdict |
|---|----------|---------|---------------|---------------|
| 1 | What are the key data types allowed in the `_meta` field of the NotificationParams? (mcp_protocol_spec) | base | 5/5/5 | agree — answer quotes the exact `{[key: string]: unknown}` shape from context |
| 2 | How can we mitigate the security risks of local MCP servers that users may install or configure? (mcp_security_docs) | practitioner | 5/5/5 | agree — threat context + consent/isolation mitigations all grounded in retrieved passages |
| 3 | How should the likelihood and magnitude of impacts from AI system use be evaluated and documented? (nist_ai_rmf) | base | 5/5/5 | agree — cites MP-5.1-001, matches gold on expected-use/incident-report criteria |
| 4 | What are the specific input validation requirements for agent input channels per the ASVS checklist? (owasp_agentic_top_10) | practitioner | 4/4/4 | agree — correct on V5.1.1; slightly broader than the single gold line, score reflects it |
| 5 | How can Retrieval-Augmented Generation (RAG) help mitigate misinformation in model outputs? (owasp_llm_top_10) | practitioner | 4/4/5 | agree — grounded in [LLM08]; adds RAG-specific risks alongside the mitigation |

_Notes:_ The judge's scores track answer quality in all five sampled pairs — high
scores correspond to answers that quote/cite the retrieved context, and the two
4-scores correspond to answers that generalize slightly beyond the single gold
line without contradicting the sources. No case of a high score masking a
hallucination was observed in the spot-check. The full per-pair judged detail is
in `evaluation/results/llm_eval_detail.json`.
