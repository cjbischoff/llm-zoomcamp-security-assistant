"""Embedding logic for chunks"""

import os
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from openai import OpenAI


class Embedder:
    """Embed chunks using text-embedding-3-small"""

    def __init__(self, model: str = "text-embedding-3-small"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model
        self.embedding_dim = 512  # text-embedding-3-small

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of texts using OpenAI API.
        Returns: list of embeddings (each 512-dim vector)
        """
        if not texts:
            return []

        response = self.client.embeddings.create(
            model=self.model,
            input=texts
        )

        return [item.embedding for item in response.data]

    def embed_chunks(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Embed a list of chunks.
        Returns: same chunks with 'embedding' field added
        """
        texts = [chunk["text"] for chunk in chunks]
        embeddings = self.embed(texts)

        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding
            chunk["embedding_model"] = self.model

        return chunks
