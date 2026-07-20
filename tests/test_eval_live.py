"""Availability-guarded end-to-end eval probe (EVL-01/02/03).

Mirrors ``tests/test_hybrid_live.py``: stacks the ``qdrant_client`` (skips when
Qdrant is unreachable) and ``openai_available`` (skips when ``OPENAI_API_KEY`` is
absent) fixtures, so it degrades to a SKIP — never an error — offline. Target
imports are deferred into the test body so an absent Wave 2/3 eval symbol can
never cause a collection-time crash.

RED / should-skip until the eval scripts are real (Waves 2-3) and a live env is
present. This is a tiny smoke probe (1 sampled pair) that proves the real-data
contract holds — it does NOT produce the headline numbers. Those come from the
Plan 04-04 live-run checkpoint into ``evaluation/EVALUATION.md``.

Contract it locks:
  1. Qdrant-scroll sampling returns chunks whose ids are strings spanning more
     than one of the five sources (the real point id is the relevance label).
  2. The retrieval eval driver in "dense" mode returns a non-empty list of
     retrieved ids that are strings in the same id space as the ground-truth
     chunk_id (the relevance join is type-compatible and actually joins).
  3. The judge path parses one generated answer to the three integer D-10
     dimensions (accuracy / completeness / hallucination).
"""


def test_eval_pipeline_smoke_live(qdrant_client, openai_available):
    """One sampled pair proves scroll-sampling, the dense retrieval join, and the judge."""
    from evaluation.generate_qa import QAGenerator, sample_chunks
    from evaluation.eval_retrieval import retrieved_ids
    from evaluation.eval_llm import LLMEvaluator

    # 1. Scroll-sample the live collection; ids are strings across >1 source.
    sampled = sample_chunks(per_source=1, seed=42)
    assert sampled, "expected sampled chunks from the populated collection"
    assert all(isinstance(c["id"], str) for c in sampled)
    assert len({c["source"] for c in sampled}) > 1

    # 2. Author a Q&A pair for one chunk; chunk_id is the real point id.
    chunk = sampled[0]
    rows = QAGenerator().generate_qa_for_chunk(
        chunk_text=chunk["text"], chunk_id=chunk["id"], source=chunk["source"]
    )
    assert rows, "expected at least one generated Q&A row"
    pair = rows[0]
    assert pair["chunk_id"] == chunk["id"]

    # 3. Dense retrieval driver returns a non-empty list of string ids (join-compatible).
    hits = retrieved_ids(pair["question"], mode="dense", top_k=5)
    assert hits, "dense retrieval returned no hits for a real question"
    assert all(isinstance(h, str) for h in hits)

    # 4. The judge parses one answer to the three integer D-10 dimensions.
    scores = LLMEvaluator().judge_answer(
        query=pair["question"], answer=pair["answer"], context=chunk["text"]
    )
    for dim in ("accuracy", "completeness", "hallucination"):
        assert isinstance(scores[dim], int)
        assert 1 <= scores[dim] <= 5
