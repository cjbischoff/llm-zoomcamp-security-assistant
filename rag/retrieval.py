"""Retrieval pipeline: Dense, BM25, and Hybrid search"""

import logging
import os
from typing import Any, Dict, List, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> List[str]:
    """Tokenize text for BM25 indexing and querying.

    A single shared tokenizer keeps the index and query token spaces aligned
    (Pitfall 4): a lowercase whitespace split. Deliberately minimal.

    Args:
        text: Raw text to tokenize.

    Returns:
        list[str]: Lowercased whitespace-split tokens.
    """
    return text.lower().split()


class DenseRetriever:
    """Dense vector search using cosine similarity"""

    def __init__(self, collection_name: Optional[str] = None):
        self.collection_name = collection_name or os.getenv("QDRANT_COLLECTION_NAME", "security_rag")
        self.qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
        self.client = QdrantClient(
            host=self.qdrant_host, port=self.qdrant_port, check_compatibility=False
        )

    def retrieve(self, query_embedding: List[float], top_k: int = 5) -> Dict[str, Any]:
        """Search the collection with an already-embedded query vector.

        Args:
            query_embedding: A 1536-dim vector (text-embedding-3-small); the
                caller does the embedding — this stays a pure vector-search unit.
            top_k: Maximum number of hits to return.

        Returns:
            ``{"status": str, "hits": [...]}`` where ``status`` is one of
            ``"ok"``, ``"collection_missing"``, ``"backend_down"``, or
            ``"backend_error"``. On ``"ok"`` each hit is
            ``{"id", "text", "score", "metadata"}`` where ``id`` is the Qdrant
            point id (the RRF join key), and ``score`` the raw cosine
            similarity (higher = better, no inversion) and ``text`` excluded
            from ``metadata``. A genuine empty result is ``ok`` with
            ``hits == []`` — an outage is never masked as an empty result.
            Status strings are the only client-facing signal; raw exception
            detail is logged, never returned (no connection strings/keys leaked).
        """
        try:
            if not self.client.collection_exists(self.collection_name):
                return {"status": "collection_missing", "hits": []}
        except ResponseHandlingException as e:
            logger.error("Qdrant backend unreachable during preflight: %s", e)
            return {"status": "backend_down", "hits": []}

        try:
            resp = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except ResponseHandlingException as e:
            logger.error("Qdrant backend unreachable during query: %s", e)
            return {"status": "backend_down", "hits": []}
        except UnexpectedResponse as e:
            logger.error("Qdrant query failed: %s", e)
            return {"status": "backend_error", "hits": []}

        hits = [
            {
                "id": p.id,
                "text": p.payload.get("text", ""),
                "score": p.score,
                "metadata": {k: v for k, v in p.payload.items() if k != "text"},
            }
            for p in resp.points
        ]
        return {"status": "ok", "hits": hits}


class BM25Retriever:
    """BM25 sparse keyword search over the chunk corpus (rank-bm25, in-memory).

    The corpus is either injected (unit-test seam) or loaded lazily once per
    process by scrolling the Qdrant collection. Uses ``BM25Okapi`` with the
    shared :func:`_tokenize` at both index and query time.

    ponytail: process-level cache, rebuilt per instance. A shared singleton is
    Phase 5 (INT-01) — do not pull forward.
    """

    def __init__(self, docs: Optional[List[Dict[str, Any]]] = None, collection_name: Optional[str] = None):
        """Build the BM25 index eagerly from ``docs``, or defer to a lazy scroll.

        Args:
            docs: Optional list of ``{"id","text","metadata"}`` docs. If given,
                the index is built immediately (unit-test seam / injection).
            collection_name: Qdrant collection to scroll when ``docs`` is None.
                Defaults to env ``QDRANT_COLLECTION_NAME``.
        """
        self.collection_name = collection_name or os.getenv("QDRANT_COLLECTION_NAME", "security_rag")
        self._bm25 = None
        self._ids: List[Any] = []
        self._docs: List[Dict[str, Any]] = []
        if docs is not None:
            self._build_index(docs)

    def _build_index(self, docs: List[Dict[str, Any]]) -> None:
        """Build the ``BM25Okapi`` index over ``docs``, keeping parallel ids/docs.

        Args:
            docs: List of ``{"id","text","metadata"}`` docs.
        """
        from rank_bm25 import BM25Okapi  # lazy: never fail import if dep absent

        self._docs = docs
        self._ids = [d["id"] for d in docs]
        self._bm25 = BM25Okapi([_tokenize(d.get("text", "")) for d in docs])

    def _ensure_index(self) -> None:
        """Load and build the corpus once by scrolling Qdrant if not already built.

        Pattern 5: page through the collection with ``scroll`` to pull all
        chunk texts + point ids into memory, then build the index. Cached on the
        instance so it runs once per process.
        """
        if self._bm25 is not None:
            return

        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", 6333))
        client = QdrantClient(host=host, port=port, check_compatibility=False)

        docs: List[Dict[str, Any]] = []
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=self.collection_name,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                payload = p.payload or {}
                docs.append({
                    "id": p.id,
                    "text": payload.get("text", ""),
                    "metadata": {k: v for k, v in payload.items() if k != "text"},
                })
            if offset is None:
                break

        self._build_index(docs)

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Rank the corpus against ``query`` by BM25 score.

        Args:
            query: Free-text query; tokenized with the shared :func:`_tokenize`.
            top_k: Maximum number of hits to return.

        Returns:
            list[dict]: Up to ``top_k`` hits ``{"id","text","score","metadata"}``
                sorted by descending BM25 score.
        """
        self._ensure_index()
        scores = self._bm25.get_scores(_tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [
            {
                "id": self._ids[i],
                "text": self._docs[i].get("text", ""),
                "score": float(scores[i]),
                "metadata": self._docs[i].get("metadata", {}),
            }
            for i in order
        ]


def rrf_fuse(
    dense_hits: List[Dict[str, Any]],
    bm25_hits: List[Dict[str, Any]],
    k: int = 60,
) -> List[Dict[str, Any]]:
    """Fuse two ranked hit lists via Reciprocal Rank Fusion, joined on point id.

    Each list contributes ``1/(k + rank)`` (1-based rank) to a doc's fused
    score. The join key is the point ``id`` (never text). Dense-first precedence:
    a doc in both legs keeps its dense hit, so the cosine ``score`` survives for
    the downstream 0.4 gate.

    Args:
        dense_hits: Dense leg hits, each ``{"id","text","score","metadata"}``.
        bm25_hits: BM25 leg hits, same shape (``score`` is the BM25 score).
        k: RRF constant (default 60).

    Returns:
        list[dict]: Fused hits sorted by descending fused score, each carrying a
            numeric ``rrf_score`` alongside the preserved original fields.
    """
    scores: Dict[Any, float] = {}
    by_id: Dict[Any, Dict[str, Any]] = {}
    for hits in (dense_hits, bm25_hits):
        for rank, hit in enumerate(hits, start=1):
            hid = hit["id"]
            scores[hid] = scores.get(hid, 0.0) + 1.0 / (k + rank)
            by_id.setdefault(hid, hit)  # dense-first precedence (cosine survives)

    ordered = sorted(scores, key=lambda hid: scores[hid], reverse=True)
    return [{**by_id[hid], "rrf_score": scores[hid]} for hid in ordered]


class Reranker:
    """Cross-encoder reranker over the fused top candidates (BON-01/BON-03).

    Wraps the pinned ``cross-encoder/ms-marco-MiniLM-L6-v2`` model, constructed
    lazily and once per instance (the first construction downloads ~80MB). The
    model id is pinned (no ``latest``/arbitrary revision) — supply-chain
    mitigation T-03-02. This method is synchronous and CPU/torch-bound; the
    off-loop wrap is the pipeline's job (Plan 03-04).
    """

    _MODEL_ID = "cross-encoder/ms-marco-MiniLM-L6-v2"

    def __init__(self):
        """Defer model construction to first use (no download at import/ctor)."""
        self._model = None

    def _get_model(self):
        """Construct and cache the pinned cross-encoder on first use.

        Returns:
            The CrossEncoder instance (lazily imported and constructed once).
        """
        if self._model is None:
            from sentence_transformers import CrossEncoder  # lazy import

            self._model = CrossEncoder(self._MODEL_ID)
        return self._model

    def rerank(
        self,
        query: str,
        fused: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Reorder the fused candidates by cross-encoder relevance to ``query``.

        Args:
            query: The raw query text.
            fused: Fused hits (RRF output); capped at the top 20 (D-05).
            top_k: Number of reranked hits to return.

        Returns:
            list[dict]: Up to ``top_k`` hits in reranked order, each carrying a
                ``rerank_score`` while preserving id/cosine ``score``/metadata.
        """
        candidates = fused[:20]
        ranks = self._get_model().rank(query, [c["text"] for c in candidates], top_k=top_k)
        return [
            {**candidates[r["corpus_id"]], "rerank_score": float(r["score"])}
            for r in ranks
        ]


class HybridRetriever:
    """Hybrid search combining dense + BM25 with RRF fusion and cross-encoder reranking"""

    def __init__(self, collection_name: Optional[str] = None):
        self.collection_name = collection_name or os.getenv("QDRANT_COLLECTION_NAME", "security_rag")
        self.dense = DenseRetriever(collection_name)
        self.bm25 = BM25Retriever(collection_name=self.collection_name)
        self._reranker = None  # lazy: built on first rerank=True call

    def retrieve(
        self,
        query_embedding: List[float],
        query_text: str,
        detected_id: Optional[str] = None,
        top_k: int = 5,
        rerank: bool = False,
    ) -> Dict[str, Any]:
        """Fuse dense + BM25 by RRF, soft-boost a detected threat, optionally rerank.

        Args:
            query_embedding: The embedded query vector (dense leg).
            query_text: The raw query text (BM25 + rerank legs).
            detected_id: An optional canonical threat id; matching chunks get a
                small rank boost (soft-boost, D-04) without dropping others.
            top_k: Number of hits to return.
            rerank: When True, reorder the fused top candidates with the
                cross-encoder reranker.

        Returns:
            ``{"status", "hits", "gate_score"}`` where ``status`` propagates the
            dense leg's status (so an outage is never masked), ``gate_score`` is
            the max dense cosine (the 0.4 gate reference — never a BM25 score),
            and each hit preserves its cosine ``score``.
        """
        dense_result = self.dense.retrieve(query_embedding, top_k=20)
        if dense_result["status"] != "ok":
            return {"status": dense_result["status"], "hits": [], "gate_score": 0.0}

        dense_hits = dense_result["hits"]
        gate_score = max((h["score"] for h in dense_hits), default=0.0)

        try:
            bm25_hits = self.bm25.retrieve(query_text, top_k=20)
            fused = rrf_fuse(dense_hits, bm25_hits, k=60)
        except Exception as e:  # noqa: BLE001 - degrade, never leak (Security V7)
            logger.error("BM25/fusion failed, falling back to dense: %s", e)
            fused = [{**h, "rrf_score": 0.0} for h in dense_hits]

        if detected_id:
            boost = 0.5 / 60
            for hit in fused:
                if hit.get("metadata", {}).get("threat_id") == detected_id:
                    hit["rrf_score"] += boost
            fused.sort(key=lambda h: h["rrf_score"], reverse=True)

        if rerank:
            try:
                if self._reranker is None:
                    self._reranker = Reranker()
                hits = self._reranker.rerank(query_text, fused, top_k=top_k)
            except Exception as e:  # noqa: BLE001 - degrade, never leak (Security V7)
                logger.error("Rerank failed, falling back to fused: %s", e)
                hits = fused[:top_k]
        else:
            hits = fused[:top_k]

        return {"status": "ok", "hits": hits, "gate_score": gate_score}
