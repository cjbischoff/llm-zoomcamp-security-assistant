"""Pure-unit RED spec for retrieval metric math (EVL-02).

Targets ``RetrieverEvaluator.evaluate_query`` (``evaluation/eval_retrieval.py``).
No network, no Qdrant — just the metric arithmetic on tiny fixtures with known
expected values. The target import is deferred into each test body per the
project RED pattern (mirrors ``tests/test_rrf.py`` / ``tests/test_query_mode.py``).

RED until Plan 04-03: the scaffold computes precision as
``sum(relevant) / len(retrieved_ids)`` (``eval_retrieval.py:43``) rather than over
the fixed ``top_k`` denominator (D-07 precision@5). Fixture (a) has 3 retrieved
ids and 1 gold hit, so the scaffold returns 1/3 == 0.333; the standard
precision@5 is 1/5 == 0.2. The precision@5 assertion is the RED-forcing case.
"""

import pytest


def test_hit_mrr_precision_at_rank_two():
    """gold at rank 2 of a short list: hit, mrr 0.5, precision@5 0.2 (RED case)."""
    from evaluation.eval_retrieval import RetrieverEvaluator

    result = RetrieverEvaluator.evaluate_query(
        query="q",
        expected_chunk_ids=["a"],
        retrieved_ids=["x", "a", "y"],
        top_k=5,
    )

    assert result["hit"] is True
    assert result["mrr"] == pytest.approx(0.5)  # first relevant at rank 2
    # RED: scaffold divides by len(retrieved)=3 -> 0.333; precision@5 must use k=5.
    assert result["precision"] == pytest.approx(0.2)


def test_hit_at_rank_one_full_list():
    """gold at rank 1 of a full top-5: hit, mrr 1.0, precision@5 0.2."""
    from evaluation.eval_retrieval import RetrieverEvaluator

    result = RetrieverEvaluator.evaluate_query(
        query="q",
        expected_chunk_ids=["a"],
        retrieved_ids=["a", "b", "c", "d", "e"],
        top_k=5,
    )

    assert result["hit"] is True
    assert result["mrr"] == pytest.approx(1.0)
    assert result["precision"] == pytest.approx(0.2)


def test_miss_returns_zeros():
    """No gold in the retrieved list: hit False, mrr 0, precision 0."""
    from evaluation.eval_retrieval import RetrieverEvaluator

    result = RetrieverEvaluator.evaluate_query(
        query="q",
        expected_chunk_ids=["z"],
        retrieved_ids=["a", "b"],
        top_k=5,
    )

    assert result["hit"] is False
    assert result["mrr"] == pytest.approx(0.0)
    assert result["precision"] == pytest.approx(0.0)


def test_empty_retrieved_returns_zeros():
    """No retrieved ids at all: hit False, mrr 0, precision 0 (no division error)."""
    from evaluation.eval_retrieval import RetrieverEvaluator

    result = RetrieverEvaluator.evaluate_query(
        query="q",
        expected_chunk_ids=["a"],
        retrieved_ids=[],
        top_k=5,
    )

    assert result["hit"] is False
    assert result["mrr"] == pytest.approx(0.0)
    assert result["precision"] == pytest.approx(0.0)
