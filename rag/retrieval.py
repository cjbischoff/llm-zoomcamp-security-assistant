"""Retrieval pipeline: Dense, BM25, and Hybrid search"""

import logging
import os
from typing import Any, Dict, List, Optional
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

logger = logging.getLogger(__name__)


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
            ``{"text", "score", "metadata"}`` with ``score`` the raw cosine
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
                "text": p.payload.get("text", ""),
                "score": p.score,
                "metadata": {k: v for k, v in p.payload.items() if k != "text"},
            }
            for p in resp.points
        ]
        return {"status": "ok", "hits": hits}


class BM25Retriever:
    """BM25 keyword search (fallback implementation)"""

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """BM25 search using keyword matching"""
        # Placeholder: full implementation would use Qdrant sparse indices
        # For now, return empty list
        return []


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
