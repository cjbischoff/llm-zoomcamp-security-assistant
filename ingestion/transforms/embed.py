"""Embedding logic for chunks."""

import os
from typing import List, Dict, Any

from openai import OpenAI

# text-embedding-3-small returns 1536-dim vectors natively (D-05/D-06). The
# collection must match this width; never narrow it via a dimensions= override.
_BATCH_SIZE = 100


class Embedder:
    """Embed chunks using text-embedding-3-small (native 1536-dim)."""

    def __init__(self, model: str = "text-embedding-3-small"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.embedding_dim = 1536  # native width of text-embedding-3-small

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed texts via OpenAI, batching large inputs.

        Sends only ``model`` and ``input`` so the API returns its native
        1536-dim vectors (no dimension-narrowing argument).

        Args:
            texts: Texts to embed.

        Returns:
            One 1536-length vector per input text, in order. Empty input
            returns ``[]`` without calling the API.
        """
        if not texts:
            return []

        vectors: List[List[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start:start + _BATCH_SIZE]
            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
            )
            vectors.extend(item.embedding for item in response.data)

        return vectors

    def embed_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add embeddings to a list of chunks.

        Args:
            chunks: Chunks in the locked ``{"text", "metadata"}`` shape.

        Returns:
            The same chunks with ``embedding`` and ``embedding_model`` added.
        """
        texts = [chunk["text"] for chunk in chunks]
        embeddings = self.embed(texts)

        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding
            chunk["embedding_model"] = self.model

        return chunks
