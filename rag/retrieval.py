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


class HybridRetriever:
    """Hybrid search combining dense + BM25 with RRF fusion and cross-encoder reranking"""

    def __init__(self, collection_name: Optional[str] = None):
        self.collection_name = collection_name or os.getenv("QDRANT_COLLECTION_NAME", "security_rag")
        self.dense = DenseRetriever(collection_name)
        self.bm25 = BM25Retriever()

    def retrieve(self, query_embedding: List[float], query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Hybrid search with RRF fusion"""
        # Get dense results (retrieve() now returns a {status, hits} channel)
        dense_results = self.dense.retrieve(query_embedding, top_k=10)["hits"]

        # Get BM25 results
        bm25_results = self.bm25.retrieve(query_text, top_k=10)

        # Combine results (simplified: just return dense for now)
        return dense_results[:top_k]
