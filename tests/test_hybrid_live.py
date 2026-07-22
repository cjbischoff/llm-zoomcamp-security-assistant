"""Availability-guarded live probe: hybrid differs from dense (SC1/SC2, RET-04).

Integration test against the populated Qdrant ``security_rag`` collection. Uses
the ``qdrant_client`` fixture (skips when Qdrant is unreachable) + ``openai_available``
(skips when the key is absent), so it degrades to a skip — never an error —
offline. Target imports are deferred into the test body.

RED until Plan 03-03: on a keyword-strong probe, hybrid (dense + BM25 + RRF) must
return a top-5 id set that differs from dense-only. The scaffold's HybridRetriever
returns ``dense[:top_k]``, so hybrid == dense (fails SC2).
"""


def test_hybrid_differs_from_dense_live(qdrant_client, openai_available):
    """A probe surfaces a hybrid top-5 id set distinct from dense-only (SC1/SC2)."""
    from ingestion.transforms.embed import Embedder
    from rag.retrieval import DenseRetriever, HybridRetriever

    probe = "unbounded consumption"  # keyword-strong; BM25 disagrees with dense
    vec = Embedder().embed([probe])[0]
    assert len(vec) == 1536

    dense = DenseRetriever().retrieve(vec, top_k=5)
    assert dense["status"] == "ok"
    dense_ids = {h["id"] for h in dense["hits"]}

    hybrid = HybridRetriever().retrieve(vec, probe, top_k=5)
    hybrid_ids = {h["id"] for h in hybrid["hits"]}

    assert hybrid_ids != dense_ids  # fusion demonstrably reorders (SC2)
