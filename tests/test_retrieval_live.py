"""Availability-guarded live probe for dense retrieval (RET-01).

Integration test against the populated Qdrant ``security_rag`` collection. It
uses the ``qdrant_client`` fixture (skips when Qdrant is unreachable) plus
``openai_available`` (skips when the key is absent), so it degrades to a skip —
never an error — offline. Target imports are deferred into the test body.

RED until Plan 02-02: a real threat-ID probe should embed at 1536, hit
``query_points``, and return ``status == "ok"`` with at least one hit carrying a
``threat_id``. The scaffold still calls the removed ``.search``.
"""


def test_threat_id_probe_returns_passage(qdrant_client, openai_available):
    """A threat-ID query returns a real graded passage with a threat_id (RET-01)."""
    from ingestion.transforms.embed import Embedder
    from rag.retrieval import DenseRetriever

    vec = Embedder().embed(["prompt injection LLM01"])[0]
    assert len(vec) == 1536

    result = DenseRetriever().retrieve(vec, top_k=5)

    assert result["status"] == "ok"
    assert len(result["hits"]) >= 1
    assert any(h["metadata"].get("threat_id") for h in result["hits"])
