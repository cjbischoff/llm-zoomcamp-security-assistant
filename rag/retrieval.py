"""Retrieval pipeline: Dense, BM25, and Hybrid search"""

import os
import time
from typing import List, Dict, Any
from qdrant_client import QdrantClient
import numpy as np


class DenseRetriever:
    """Dense vector search using cosine similarity"""

    def __init__(self, collection_name: str = None):
        self.collection_name = collection_name or os.getenv("QDRANT_COLLECTION_NAME", "security_rag")
        self.qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
        self.client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)

    def retrieve(self, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Search using dense vector similarity"""
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k
            )

            return [
                {
                    "text": result.payload.get("text", ""),
                    "score": result.score,
                    "metadata": {k: v for k, v in result.payload.items() if k != "text" and k != "embedding"}
                }
                for result in results
            ]
        except Exception as e:
            print(f"Dense retrieval error: {e}")
            return []


class BM25Retriever:
    """BM25 keyword search (fallback implementation)"""

    def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """BM25 search using keyword matching"""
        # Placeholder: full implementation would use Qdrant sparse indices
        # For now, return empty list
        return []


class HybridRetriever:
    """Hybrid search combining dense + BM25 with RRF fusion and cross-encoder reranking"""

    def __init__(self, collection_name: str = None):
        self.collection_name = collection_name or os.getenv("QDRANT_COLLECTION_NAME", "security_rag")
        self.dense = DenseRetriever(collection_name)
        self.bm25 = BM25Retriever()

    def retrieve(self, query_embedding: List[float], query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Hybrid search with RRF fusion"""
        # Get dense results
        dense_results = self.dense.retrieve(query_embedding, top_k=10)

        # Get BM25 results
        bm25_results = self.bm25.retrieve(query_text, top_k=10)

        # Combine results (simplified: just return dense for now)
        return dense_results[:top_k]
