"""Thin end-to-end evaluation orchestrator (EVL-01..04, D-11).

Wires the three Wave-2 eval lines against the REAL 850-doc ``security_rag``
collection and assembles a single grader-readable ``evaluation/EVALUATION.md``:

1. Ground truth — ``generate_qa.generate_all_qa`` (only if the CSV is absent;
   a committed CSV is the single source of truth, D-03).
2. Retrieval — ``eval_retrieval.RetrieverEvaluator.evaluate_all`` across the
   three modes; the winner is picked by hit-rate then MRR (D-06/D-08).
3. LLM-as-judge — for each pair, retrieve full hits via the WINNING mode,
   reassemble the pipeline's numbered ``[threat_id] (source:)`` context so the
   judge scores against exactly what the generator saw (Pitfall 4), generate
   an answer for each prompt variant, and score it with the ``gpt-4o`` judge
   (D-09/D-10).

No new algorithms live here — this module only orchestrates and formats. Any
per-pair OpenAI/Qdrant failure degrades non-leaking (log server-side, continue)
so one bad pair never aborts the whole run (T-04-05). Importing this module
never constructs an OpenAI/Qdrant client — every heavy import is deferred into
the functions, so ``import evaluation.run_eval`` stays offline-safe.
"""

import argparse
import asyncio
import json
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

DEFAULT_GT = "evaluation/ground_truth.csv"
DEFAULT_REPORT = "evaluation/EVALUATION.md"
DEFAULT_RESULTS_DIR = "evaluation/results"
_MODES = ("dense", "hybrid", "hybrid_rerank")
_VARIANTS = ("base", "practitioner")


def assemble_context(hits: List[Dict[str, Any]]) -> str:
    """Reassemble the pipeline's numbered citation context from retrieved hits.

    Mirrors ``rag/pipeline.py`` (Step 4, lines 127-132) exactly so the judge
    scores the answer against the SAME context block the generator saw — the
    hallucination dimension is only meaningful against the real generation
    context (research Pitfall 4).

    Args:
        hits: Retriever hit dicts, each carrying ``text`` and a ``metadata``
            mapping with ``threat_id`` / ``source``.

    Returns:
        str: The numbered ``[threat_id] (source: ...)\\n<text>`` passages joined
            by blank lines — byte-identical in shape to the production context.
    """
    return "\n\n".join(
        f"[{h['metadata'].get('threat_id', '?')}] "
        f"(source: {h['metadata'].get('source', '?')})\n{h['text']}"
        for h in hits
    )


def _drain_answer(generator, query: str, context: str, variant: str) -> str:
    """Drain the async streaming generator into a full answer string.

    Runs the async generator on a fresh event loop with ``asyncio.run`` (the
    same drain idiom as the ``collect_stream`` test fixture), so the streaming
    production generator can be exercised from this synchronous orchestrator.

    Args:
        generator: An ``rag.generator.LLMGenerator`` instance.
        query: The raw ground-truth question.
        context: The assembled numbered context passages.
        variant: ``"base"`` or ``"practitioner"``.

    Returns:
        str: The full concatenated answer.
    """

    async def _collect() -> str:
        return "".join(
            [
                tok
                async for tok in generator.stream_answer(
                    query=query, context=context, prompt_variant=variant
                )
            ]
        )

    return asyncio.run(_collect())


def pick_winner(retrieval_results: Dict[str, Dict[str, float]]) -> str:
    """Pick the winning retrieval mode by hit-rate, MRR as tie-breaker (D-08).

    Args:
        retrieval_results: ``{mode: {"hit_rate","mrr","precision"}}`` aggregates.

    Returns:
        str: The mode with the highest ``(hit_rate, mrr)`` tuple.
    """
    return max(
        retrieval_results,
        key=lambda m: (retrieval_results[m]["hit_rate"], retrieval_results[m]["mrr"]),
    )


def run_judge_line(
    ground_truth: List[Dict[str, Any]],
    winner_mode: str,
    results_dir: str = DEFAULT_RESULTS_DIR,
) -> tuple:
    """Generate answers for both variants over the winning mode and judge them.

    For each ground-truth pair: retrieve full hits via the winner mode,
    reassemble the numbered context, then for each prompt variant generate the
    production answer and score it with the ``gpt-4o`` judge. A per-pair failure
    is logged server-side and skipped (T-04-05) — never aborts the run.

    Args:
        ground_truth: Loaded ground-truth rows (``question``/``answer``/...).
        winner_mode: The retrieval mode chosen as the production default.
        results_dir: Where to write the detailed judged records JSON.

    Returns:
        tuple: ``(aggregates, detail_records)`` where ``aggregates`` is the
            per-variant mean-score dict from ``LLMEvaluator.evaluate_variants``
            and ``detail_records`` is the per-pair list (question, answer,
            context, gold, scores) used to build the human spot-check.
    """
    from evaluation.eval_llm import LLMEvaluator
    from evaluation.eval_retrieval import retrieve_hits
    from rag.generator import LLMGenerator

    judge = LLMEvaluator()
    generator = LLMGenerator()

    judged_records: List[Dict[str, Any]] = []
    detail_records: List[Dict[str, Any]] = []

    for row in ground_truth:
        question = row["question"]
        gold = row.get("answer", "")
        try:
            hits = retrieve_hits(question, winner_mode, top_k=5)
        except Exception:
            logger.error("Retrieval failed for a pair — skipping", exc_info=True)
            continue
        context = assemble_context(hits)

        for variant in _VARIANTS:
            try:
                answer = _drain_answer(generator, question, context, variant)
                scores = judge.judge_answer(question, answer, context, gold)
            except Exception:
                logger.error("Judge/generation failed for a pair — skipping", exc_info=True)
                continue
            judged_records.append({"variant": variant, **scores})
            detail_records.append(
                {
                    "variant": variant,
                    "question": question,
                    "gold_answer": gold,
                    "answer": answer,
                    "context": context,
                    **scores,
                }
            )

    aggregates = judge.evaluate_variants(
        judged_records, output_file=os.path.join(results_dir, "llm_eval.csv")
    )

    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, "llm_eval_detail.json"), "w") as f:
        json.dump(detail_records, f, indent=2)

    return aggregates, detail_records


def _per_source_counts(ground_truth: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count ground-truth rows per source for the report."""
    counts: Dict[str, int] = {}
    for row in ground_truth:
        counts[row.get("source", "unknown")] = counts.get(row.get("source", "unknown"), 0) + 1
    return counts


def build_report(
    ground_truth: List[Dict[str, Any]],
    retrieval_results: Dict[str, Dict[str, float]],
    winner_mode: str,
    judge_aggregates: Dict[str, Dict[str, float]],
    gt_path: str = DEFAULT_GT,
) -> str:
    """Assemble the grader-readable ``EVALUATION.md`` body (D-11).

    Emits every required section heading (Methodology, Ground Truth, Retrieval
    Metrics, Chosen Production Mode, LLM-as-Judge, Human Spot-Check) including
    the single-gold precision@5 bound note and the circularity discussion.

    Args:
        ground_truth: Loaded ground-truth rows.
        retrieval_results: ``{mode: {"hit_rate","mrr","precision"}}`` aggregates.
        winner_mode: The mode chosen as the production default.
        judge_aggregates: ``{variant: {"accuracy","completeness","hallucination"}}``.
        gt_path: Path to the committed ground-truth CSV (referenced in the report).

    Returns:
        str: The full Markdown report body.
    """
    counts = _per_source_counts(ground_truth)
    src_lines = "\n".join(f"| {src} | {n} |" for src, n in sorted(counts.items()))

    ret_rows = "\n".join(
        f"| {mode} | {m['hit_rate']:.2%} | {m['mrr']:.3f} | {m['precision']:.3f} |"
        for mode, m in retrieval_results.items()
    )

    judge_rows = "\n".join(
        f"| {variant} | {s['accuracy']:.2f} | {s['completeness']:.2f} | {s['hallucination']:.2f} |"
        for variant, s in judge_aggregates.items()
    )

    latency_note = {
        "dense": "`dense` is the fast interactive path — a single Qdrant cosine query, "
        "no extra model. Chosen as the production default.",
        "hybrid": "`hybrid` adds BM25 + reciprocal-rank fusion over the dense results "
        "(no extra model download, modest CPU cost).",
        "hybrid_rerank": "`hybrid_rerank` adds an ~80MB cross-encoder download and "
        "per-query rerank latency on top of hybrid — the metric win must justify that cost.",
    }.get(winner_mode, winner_mode)

    return f"""# Evaluation Report — Security RAG Assistant

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
label the retrieval join depends on. The committed CSV (`{gt_path}`) is the
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
most 1 of the top-5 can be relevant: precision@5 ∈ {0, 0.2} per query and its
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

- Total pairs: **{len(ground_truth)}**
- CSV path: `{gt_path}` (committed)
- Per-source counts:

| Source | Pairs |
|--------|-------|
{src_lines}

## Retrieval Metrics

Hit-rate / MRR / precision@5 across the three modes on the ground-truth set:

| Mode | Hit Rate | MRR | Precision@5 |
|------|----------|-----|-------------|
{ret_rows}

## Chosen Production Mode

**Winner: `{winner_mode}`** (selected by hit-rate, MRR as tie-breaker — D-08).

{latency_note}

The winning mode is wired as the production default `retrieval_mode` in both
`rag/pipeline.py` and `api/main.py` (kept in sync — research Pitfall 5), or, if
`dense` wins, the current default stands and that is recorded as the finding
(D-08 explicitly allows this).

## LLM-as-Judge

Mean judge scores (1-5, higher is better) per prompt variant over the winning
mode's retrieved context:

| Variant | Accuracy | Completeness | Hallucination (grounded) |
|---------|----------|--------------|--------------------------|
{judge_rows}

## Human Spot-Check

A ~5-pair human calibration of the judge (the human half of the circularity
mitigation, D-10). A reviewer reads each (question, retrieved context, generated
answer, judge scores) tuple and records agree/disagree per dimension.

| # | Question | Variant | Judge (A/C/H) | Human verdict |
|---|----------|---------|---------------|---------------|
| _to be filled at the live-run checkpoint_ | | | | |

_Notes:_ _to be filled at the live-run checkpoint._
"""


_SPOT_CHECK_HEADING = "## Human Spot-Check"


def _preserve_spot_check(new_report: str, existing_path: str) -> str:
    """Splice an existing report's Human Spot-Check section into a fresh report.

    ``build_report`` always emits the spot-check as an empty placeholder, but the
    committed ``EVALUATION.md`` carries a manually authored spot-check table +
    notes — the human half of the D-10 circularity mitigation. Regeneration must
    NOT clobber that graded content (WR-03). The spot-check is the final section,
    so we replace everything from ``## Human Spot-Check`` onward in the new
    report with the same tail from the existing file.

    Args:
        new_report: The freshly generated report body (placeholder spot-check).
        existing_path: Path to the currently committed report, if any.

    Returns:
        str: ``new_report`` with its placeholder spot-check replaced by the
            existing file's hand-filled section. Returned unchanged when there is
            no existing file or neither side has the heading.
    """
    if not os.path.exists(existing_path):
        return new_report
    with open(existing_path) as f:
        old = f.read()
    if _SPOT_CHECK_HEADING not in old or _SPOT_CHECK_HEADING not in new_report:
        return new_report
    return (
        new_report[: new_report.index(_SPOT_CHECK_HEADING)]
        + old[old.index(_SPOT_CHECK_HEADING) :]
    )


def run(
    gt_path: str = DEFAULT_GT,
    report_path: str = DEFAULT_REPORT,
    results_dir: str = DEFAULT_RESULTS_DIR,
    per_source: int = 8,
    seed: int = 42,
    pairs_cap: int = 0,
) -> Dict[str, Any]:
    """Run the full evaluation and write the report + intermediate results.

    Args:
        gt_path: Ground-truth CSV path (generated if absent).
        report_path: Where to write ``EVALUATION.md``.
        results_dir: Directory for intermediate JSON/CSV results.
        per_source: Max chunks sampled per source when generating ground truth.
        seed: Deterministic sampling seed.
        pairs_cap: If > 0, cap the ground truth to the first N pairs (fast smoke
            runs); 0 uses the full set.

    Returns:
        dict: ``{"winner", "retrieval", "judge", "n_pairs"}`` summary.
    """
    from evaluation.eval_retrieval import RetrieverEvaluator
    from evaluation.generate_qa import QAGenerator

    if not os.path.exists(gt_path):
        logger.info("Ground truth absent — generating %s", gt_path)
        QAGenerator().generate_all_qa(output_file=gt_path, per_source=per_source, seed=seed)

    evaluator = RetrieverEvaluator()
    ground_truth = evaluator.load_ground_truth(gt_path)
    if not ground_truth:
        raise RuntimeError(f"No ground-truth data at {gt_path}")
    if pairs_cap > 0:
        ground_truth = ground_truth[:pairs_cap]

    # Drive retrieval over the SAME (possibly --pairs-capped) rows the judge
    # line uses, so a smoke run stays fast and the report is internally
    # consistent (WR-01) — never silently re-expanding to the full CSV.
    retrieval_results = evaluator.evaluate_all(
        gt_path,
        modes=_MODES,
        output_file=os.path.join(results_dir, "retrieval_eval.json"),
        rows=ground_truth,
    )
    if retrieval_results is None:
        raise RuntimeError("Retrieval evaluation returned no results")

    winner = pick_winner(retrieval_results)
    logger.info("Winning retrieval mode: %s", winner)

    judge_aggregates, _detail = run_judge_line(ground_truth, winner, results_dir=results_dir)

    report = build_report(ground_truth, retrieval_results, winner, judge_aggregates, gt_path=gt_path)
    # Never overwrite a hand-filled Human Spot-Check with the placeholder (WR-03).
    report = _preserve_spot_check(report, report_path)
    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report → {report_path}  (winner: {winner})")

    return {
        "winner": winner,
        "retrieval": retrieval_results,
        "judge": judge_aggregates,
        "n_pairs": len(ground_truth),
    }


def main() -> None:
    """CLI entry: ``python -m evaluation.run_eval`` (flags for sampling/cap)."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Run the full RAG evaluation harness")
    parser.add_argument("--per-source", type=int, default=8, help="Max chunks sampled per source")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic sampling seed")
    parser.add_argument("--pairs", type=int, default=0, help="Cap ground truth to first N pairs (0 = all)")
    parser.add_argument("--ground-truth", default=DEFAULT_GT, help="Ground-truth CSV path")
    parser.add_argument("--report", default=DEFAULT_REPORT, help="Output report path")
    args = parser.parse_args()

    run(
        gt_path=args.ground_truth,
        report_path=args.report,
        per_source=args.per_source,
        seed=args.seed,
        pairs_cap=args.pairs,
    )


if __name__ == "__main__":
    main()
