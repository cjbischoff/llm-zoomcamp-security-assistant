"""Generate ground truth Q&A pairs using LLM.

Ground truth is sampled by scrolling the live Qdrant collection (source of
truth) so each row carries the REAL uuid5 point id as ``chunk_id`` — the
relevance-join key the retrieval eval depends on (Research Pitfall 1). The
scaffold's ``data/chunks.json`` read and ``chunk_id=i`` enumeration index are
gone: an int index never matches a retrieved hit's uuid and silently zeroes
every retrieval metric.
"""

import argparse
import csv
import json
import os
import random
from collections import defaultdict
from typing import Any, Dict, List, Optional

from openai import OpenAI


def _group_and_sample(
    by_source: Dict[str, List[Dict[str, Any]]],
    per_source: int = 8,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Seeded per-source sample from grouped chunks (pure, deterministic).

    Shuffles each source's chunk list with a seeded ``random.Random`` and takes
    the first ``per_source`` chunks, so repeated calls with the same seed return
    the same selection. No I/O — unit-testable in isolation.

    Args:
        by_source: Mapping of source name -> list of chunk dicts, each carrying
            at least ``"id"`` (real point id) and ``"source"``.
        per_source: Maximum chunks to take per source. Sources with fewer
            chunks contribute all they have.
        seed: Seed for the deterministic shuffle.

    Returns:
        list[dict]: Concatenation of the first ``per_source`` shuffled chunks
            per source, with each chunk's original ``id``/``source`` preserved.
    """
    rng = random.Random(seed)
    sampled: List[Dict[str, Any]] = []
    for source in sorted(by_source):  # stable source order for reproducibility
        chunks = list(by_source[source])
        rng.shuffle(chunks)
        sampled.extend(chunks[:per_source])
    return sampled


def sample_chunks(
    client: Optional[Any] = None,
    collection: Optional[str] = None,
    per_source: int = 8,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """Scroll the Qdrant collection and seeded-sample chunks per source.

    Mirrors ``rag.retrieval.BM25Retriever._ensure_index``: pages the collection
    with ``scroll`` until the offset is exhausted, capturing each point's REAL
    id + source, then delegates to :func:`_group_and_sample`. The point id is
    the relevance label the retrieval join needs — never an enumeration index.

    Args:
        client: A ``QdrantClient`` (injectable seam for offline unit tests). When
            ``None``, one is constructed from ``QDRANT_HOST``/``QDRANT_PORT``.
        collection: Collection name; defaults to ``QDRANT_COLLECTION_NAME`` env
            (``security_rag``).
        per_source: Max chunks per source (D-01 ~6-8 across the 5 corpora).
        seed: Seed for the deterministic per-source sample.

    Returns:
        list[dict]: Sampled chunk dicts ``{"id","text","source"}`` with the real
            point id preserved as ``id``.
    """
    if collection is None:
        collection = os.getenv("QDRANT_COLLECTION_NAME", "security_rag")
    if client is None:
        from qdrant_client import QdrantClient  # lazy: offline unit tests inject a client

        client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", 6333)),
            check_compatibility=False,
        )

    by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in points:
            payload = p.payload or {}
            source = payload.get("source", "unknown")
            by_source[source].append(
                {"id": p.id, "text": payload.get("text", ""), "source": source}
            )
        if offset is None:
            break

    return _group_and_sample(by_source, per_source, seed)


class QAGenerator:
    """Generate Q&A pairs for evaluation"""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model

    def generate_qa_for_chunk(self, chunk_text: str, chunk_id: str, source: str) -> List[Dict]:
        """Generate 1-2 Q&A pairs for a chunk"""
        prompt = f"""Given this security documentation chunk, generate 1-2 realistic questions
a security engineer might ask to retrieve this information.

Chunk ID: {chunk_id}
Source: {source}
Text: {chunk_text[:1000]}

Output as JSON array:
[
  {{"question": "...", "answer": "...", "chunk_id": "{chunk_id}", "source": "{source}"}}
]

Generate practical questions (not trivial). Be concise."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300
            )

            content = response.choices[0].message.content
            # Parse JSON response
            start = content.find('[')
            end = content.rfind(']') + 1
            if start >= 0 and end > start:
                qa_data = json.loads(content[start:end])
                return qa_data if isinstance(qa_data, list) else [qa_data]
            return []
        except Exception as e:
            print(f"Error generating Q&A: {e}")
            return []

    def generate_all_qa(self, chunks_file: str, output_file: str = "evaluation/ground_truth.csv"):
        """Generate Q&A for all chunks in JSON file"""
        # Load chunks
        if not os.path.exists(chunks_file):
            print(f"Chunks file not found: {chunks_file}")
            return

        with open(chunks_file) as f:
            chunks = json.load(f)

        all_qa = []
        for i, chunk in enumerate(chunks):
            print(f"Generating Q&A for chunk {i+1}/{len(chunks)}...")
            qa_pairs = self.generate_qa_for_chunk(
                chunk.get("text", ""),
                chunk_id=i,
                source=chunk.get("metadata", {}).get("source", "unknown")
            )
            all_qa.extend(qa_pairs)

        # Save as CSV
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["question", "answer", "chunk_id", "source"])
            writer.writeheader()
            writer.writerows(all_qa)

        print(f"Generated {len(all_qa)} Q&A pairs → {output_file}")


if __name__ == "__main__":
    generator = QAGenerator()
    generator.generate_all_qa("data/chunks.json")
