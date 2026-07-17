"""RED contract for manual Reciprocal Rank Fusion (RET-04).

Pure-unit, no network. The target ``rrf_fuse`` is a module-level function in
``rag.retrieval`` (created in Plan 03-03); the import is deferred INTO each test
body so a not-yet-real symbol fails RED (ImportError inside the body → clean
FAILURE), never at collection time.

Contracts encoded (RESEARCH §Pattern 2):
  * Fusion sums ``1/(k + rank)`` per list with ``k=60`` and 1-based rank.
  * The join is on the point ``id`` (stable identity), never on ``text``.
  * A doc present in BOTH input lists outranks one present in only one list.
  * Every fused hit carries a numeric ``rrf_score``.
  * Each hit's original dense cosine ``score`` survives fusion (the 0.4 gate
    is defined on cosine, not on ``rrf_score`` — Pitfall 3).
"""


def _dense():
    """Dense leg: three hits, cosine scores descending."""
    return [
        {"id": "d1", "text": "alpha", "score": 0.90, "metadata": {}},
        {"id": "shared", "text": "beta", "score": 0.70, "metadata": {"threat_id": "LLM01"}},
        {"id": "d3", "text": "gamma", "score": 0.50, "metadata": {}},
    ]


def _bm25():
    """BM25 leg: a DIFFERENT order; ``shared`` appears in both legs."""
    return [
        {"id": "shared", "text": "beta", "score": 8.1, "metadata": {"threat_id": "LLM01"}},
        {"id": "b2", "text": "delta", "score": 4.2, "metadata": {}},
        {"id": "d3", "text": "gamma", "score": 1.3, "metadata": {}},
    ]


def test_fuses_on_id_with_known_order():
    """Two ranked lists fuse into the score order given by summing 1/(k+rank)."""
    from rag.retrieval import rrf_fuse

    fused = rrf_fuse(_dense(), _bm25(), k=60)

    # 'shared' is rank 2 in dense and rank 1 in bm25: 1/62 + 1/61 — the highest sum.
    assert fused[0]["id"] == "shared"
    # rrf_score must equal the hand-computed sum for the top doc.
    assert abs(fused[0]["rrf_score"] - (1 / 62 + 1 / 61)) < 1e-9


def test_doc_in_both_lists_outranks_single_list_doc():
    """A doc present in both legs beats a doc present in only one, other things equal."""
    from rag.retrieval import rrf_fuse

    fused = rrf_fuse(_dense(), _bm25(), k=60)
    order = [h["id"] for h in fused]

    # 'shared' (both legs) must precede 'd1' (dense-only rank 1).
    assert order.index("shared") < order.index("d1")


def test_join_is_on_id_not_text():
    """Identical text under different ids does NOT collapse — the join key is id."""
    from rag.retrieval import rrf_fuse

    dense = [{"id": "x", "text": "same words", "score": 0.9, "metadata": {}}]
    bm25 = [{"id": "y", "text": "same words", "score": 5.0, "metadata": {}}]

    fused = rrf_fuse(dense, bm25, k=60)
    ids = {h["id"] for h in fused}
    assert ids == {"x", "y"}  # two distinct docs, not merged on shared text


def test_preserves_rrf_score_and_cosine_score():
    """Every hit carries a numeric rrf_score AND its original cosine score."""
    from rag.retrieval import rrf_fuse

    fused = rrf_fuse(_dense(), _bm25(), k=60)
    for hit in fused:
        assert isinstance(hit["rrf_score"], float)
        assert "score" in hit  # original cosine survives (gate is on cosine)
