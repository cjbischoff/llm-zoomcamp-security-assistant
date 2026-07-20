"""Evaluate retrieval quality: Hit Rate, MRR, Precision@5 across all three modes.

Drives the real production retrievers (``rag/retrieval.py``) over a committed
ground-truth CSV, joining each retrieved hit's Qdrant point ``id`` against the
ground-truth ``chunk_id`` (D-06). Metrics are hand-rolled: hit-rate@k,
reciprocal rank, and precision@k over a single gold chunk are three lines of
arithmetic, and scikit-learn provides no ``hit_rate@k``/``MRR@k`` primitive, so
adding it here buys nothing and drags in the deferred numpy-2.x reconciliation
(D-05 reconciliation → hand-rolled math).
"""

import csv
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lazy module-level singletons so importing this module never constructs an
# OpenAI/Qdrant client (the pure-unit metric tests import RetrieverEvaluator).
# The reranker's ~80MB download then happens at most once per process.
_embedder = None
_dense = None
_hybrid = None


def _get_retrievers():
    """Lazily construct and cache the shared Embedder + retrievers.

    Returns:
        tuple: ``(embedder, dense_retriever, hybrid_retriever)``, each built once
            per process. Constructing them here (not at import) keeps the pure
            metric unit tests network-free.
    """
    global _embedder, _dense, _hybrid
    if _embedder is None:
        from ingestion.transforms.embed import Embedder
        from rag.retrieval import DenseRetriever, HybridRetriever

        _embedder = Embedder()
        _dense = DenseRetriever()
        _hybrid = HybridRetriever()
    return _embedder, _dense, _hybrid


def retrieve_result(question: str, mode: str, top_k: int = 5) -> Dict[str, Any]:
    """Retrieve the FULL retriever result dict (hits + status + gate_score).

    Embeds the raw question once and drives the real retrievers so retrieval is
    run a single time. The comparison is kept uniform across modes (raw-question
    embed, ``detected_id=None``) so mode differences reflect retrieval quality,
    not the rewriter's soft-boost (research Open Question 2).

    The returned ``gate_score`` is the DENSE COSINE reference — never a fusion or
    cross-encoder score — matching the 0.4 grounding gate in
    ``rag/pipeline.py`` (Pitfall 3): dense mode uses the top hit's cosine, the
    hybrid modes read the retriever's own ``gate_score``. This lets the judge
    line optionally mirror the production gate (WR-04).

    Args:
        question: The raw ground-truth question.
        mode: One of ``"dense"``, ``"hybrid"``, ``"hybrid_rerank"``.
        top_k: Number of hits to return.

    Returns:
        dict: The retriever's result dict with a ``gate_score`` key guaranteed.
    """
    embedder, dense, hybrid = _get_retrievers()
    qvec = embedder.embed([question])[0]  # 1536-dim, matches the collection
    if mode == "dense":
        result = dense.retrieve(qvec, top_k=top_k)
        # The dense top-hit score IS the cosine reference the production gate reads.
        result.setdefault("gate_score", result["hits"][0]["score"] if result["hits"] else 0.0)
    else:  # hybrid | hybrid_rerank
        result = hybrid.retrieve(
            qvec, question, detected_id=None, top_k=top_k, rerank=(mode == "hybrid_rerank")
        )
    return result


def retrieve_hits(question: str, mode: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Retrieve the full hit dicts for ``question`` in the given ``mode``.

    Thin wrapper over :func:`retrieve_result` that drops the envelope and returns
    just the hits (the retrieval eval only needs the joined ids).

    Args:
        question: The raw ground-truth question.
        mode: One of ``"dense"``, ``"hybrid"``, ``"hybrid_rerank"``.
        top_k: Number of hits to return.

    Returns:
        list[dict]: The retriever's hit dicts (``{"id","text","score",...}``), or
            ``[]`` when the retriever status is not ``"ok"`` (RET-02 — an outage
            yields no hits and is logged, never silently scored as a miss).
    """
    result = retrieve_result(question, mode, top_k)
    if result["status"] != "ok":
        logger.warning("Retrieval status %r for mode %r — scoring as no hits", result["status"], mode)
        return []
    return result["hits"]


def retrieved_ids(question: str, mode: str, top_k: int = 5) -> List[Any]:
    """Return just the retrieved point ids for ``question`` in ``mode``.

    Thin wrapper over :func:`retrieve_hits` (the relevance-join key is the point
    ``id``). Returns ``[]`` on a non-ok retriever status (RET-02).

    Args:
        question: The raw ground-truth question.
        mode: One of ``"dense"``, ``"hybrid"``, ``"hybrid_rerank"``.
        top_k: Number of ids to return.

    Returns:
        list: The retrieved hits' point ids (joined against ground-truth
            ``chunk_id``), or ``[]`` on an outage.
    """
    return [h["id"] for h in retrieve_hits(question, mode, top_k)]


class RetrieverEvaluator:
    """Evaluate retrieval approaches"""

    @staticmethod
    def load_ground_truth(csv_file: str) -> List[Dict]:
        """Load ground truth Q&A pairs"""
        if not os.path.exists(csv_file):
            print(f"Ground truth file not found: {csv_file}")
            return []

        with open(csv_file) as f:
            return list(csv.DictReader(f))

    @staticmethod
    def evaluate_query(
        query: str,
        expected_chunk_ids: List[str],
        retrieved_ids: List[str],
        top_k: int = 5
    ) -> Dict:
        """Evaluate a single query"""
        retrieved_ids = retrieved_ids[:top_k]

        # Hit rate: is any expected chunk in top-k?
        hit = any(cid in retrieved_ids for cid in expected_chunk_ids)

        # MRR: 1/rank of first relevant chunk
        mrr = 0.0
        for rank, retrieved_id in enumerate(retrieved_ids, 1):
            if retrieved_id in expected_chunk_ids:
                mrr = 1.0 / rank
                break

        # Precision@k: relevant hits over the fixed top_k denominator (D-07). With
        # a single gold chunk this is bounded at 1/top_k (0.2 for k=5) — expected,
        # not a bug (research Pitfall 2); MRR is the sharper rank signal.
        relevant = sum(1 for rid in retrieved_ids if rid in expected_chunk_ids)
        precision = relevant / top_k if top_k else 0.0

        return {"hit": hit, "mrr": mrr, "precision": precision}

    def evaluate_all(
        self,
        ground_truth_file: str,
        modes: tuple = ("dense", "hybrid", "hybrid_rerank"),
        output_file: str = "evaluation/results/retrieval_eval.json",
        rows: Optional[List[Dict]] = None,
    ) -> Optional[Dict[str, Dict[str, float]]]:
        """Evaluate every ground-truth pair across all three retrieval modes.

        For each mode, drives the real retrievers over every ground-truth
        question (joining retrieved hit ``id`` against ``chunk_id``) and averages
        hit-rate, MRR, and precision@5. Real numbers only — no placeholders.

        Args:
            ground_truth_file: Path to the committed ground-truth CSV (columns
                include ``question`` and ``chunk_id``). Ignored when ``rows`` is
                supplied.
            modes: Retrieval modes to compare.
            output_file: Where to write the per-mode aggregate JSON.
            rows: Pre-loaded ground-truth rows. When provided, these are used
                as-is and the CSV is NOT re-read — so a caller-applied ``--pairs``
                cap is honored instead of silently re-expanding to the full file
                (WR-01).

        Returns:
            dict | None: ``{mode: {"hit_rate","mrr","precision"}}`` (also written
                to ``output_file``), or ``None`` if there is no ground-truth data.
        """
        ground_truth = rows if rows is not None else self.load_ground_truth(ground_truth_file)

        if not ground_truth:
            print("No ground truth data to evaluate")
            return None

        results: Dict[str, Dict[str, float]] = {}
        for mode in modes:
            per_query = [
                self.evaluate_query(
                    row["question"],
                    [row["chunk_id"]],
                    retrieved_ids(row["question"], mode, top_k=5),
                    top_k=5,
                )
                for row in ground_truth
            ]
            n = len(per_query)
            results[mode] = {
                "hit_rate": sum(r["hit"] for r in per_query) / n,
                "mrr": sum(r["mrr"] for r in per_query) / n,
                "precision": sum(r["precision"] for r in per_query) / n,
            }

        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)

        print(f"Evaluation results → {output_file}")
        for mode, metrics in results.items():
            print(f"  {mode}: Hit={metrics['hit_rate']:.2%}, MRR={metrics['mrr']:.3f}")
        return results


if __name__ == "__main__":
    evaluator = RetrieverEvaluator()
    evaluator.evaluate_all("evaluation/ground_truth.csv")
