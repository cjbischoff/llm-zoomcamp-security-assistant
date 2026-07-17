"""Availability-guarded live probe: the cross-encoder reorders (BON-03).

Integration test against the populated Qdrant ``security_rag`` collection AND a
real cross-encoder. Guarded by ``qdrant_client`` + ``openai_available`` +
``cross_encoder_available`` so it degrades to a skip — never an error — when the
infra or the dependency is absent. SLOW: the first run downloads the canonical
model ``cross-encoder/ms-marco-MiniLM-L6-v2`` (~80MB) to ~/.cache/huggingface;
cached afterwards. Target imports are deferred into the test body.

RED until Plan 03-03: reranking the fused top-20 must change the top-5 id order
versus the pre-rerank fused order on AT LEAST ONE probe (reorder is deliberate,
not guaranteed per query — the probes are chosen keyword-strong-but-semantically
-weak so the cross-encoder disagrees with RRF).
"""

import pytest

pytestmark = pytest.mark.slow


def test_rerank_reorders_live(qdrant_client, openai_available, cross_encoder_available):
    """On >=1 probe, reranked top-5 id order differs from the fused top-5 order (BON-03)."""
    from ingestion.transforms.embed import Embedder
    from rag.retrieval import HybridRetriever

    probes = [
        "unbounded consumption",
        "supply chain",
        "excessive agency",
    ]
    hybrid = HybridRetriever()
    embedder = Embedder()

    reordered_on_some_probe = False
    for probe in probes:
        vec = embedder.embed([probe])[0]
        fused = hybrid.retrieve(vec, probe, top_k=5)["hits"]
        reranked = hybrid.retrieve(vec, probe, top_k=5, rerank=True)["hits"]
        if [h["id"] for h in fused] != [h["id"] for h in reranked]:
            reordered_on_some_probe = True
            break

    assert reordered_on_some_probe  # the cross-encoder demonstrably reorders (BON-03)
