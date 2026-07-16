"""dlt pipeline orchestration script.

Two-stage ingestion: Stage 1 runs the 5 dlt resources into Postgres staging
(continue-and-report); Stage 2 reads staging, chunks, embeds at 1536 dim, and
upserts deterministic content-hash points into an explicit 1536/cosine Qdrant
collection, then verifies a non-zero exact count.
"""

import os
import sys
import uuid
import hashlib
import argparse
import logging
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Native width of text-embedding-3-small (D-05/D-06). The Qdrant collection MUST
# match this — the scaffold's 512 default is the documented dimension landmine.
EMBEDDING_DIM = 1536


def point_id(source: str, position: int, text: str) -> str:
    """Return a deterministic, Qdrant-legal point ID for a chunk.

    Hashes ``f"{source}:{position}:{text}"`` with SHA-256 and wraps the hex
    digest in a UUID5 so re-running ingestion overwrites the same point rather
    than duplicating it (D-07, ING-05). A raw hex digest is NOT a valid Qdrant
    ID — it must be an unsigned int64 or a UUID string — hence the uuid5 wrap.

    Args:
        source: Source identifier (e.g. ``owasp_llm``).
        position: Chunk position within the source (0-based).
        text: The chunk text.

    Returns:
        A UUID string, stable for identical inputs and sensitive to both
        ``position`` and ``text``.
    """
    digest = hashlib.sha256(f"{source}:{position}:{text}".encode()).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, digest))


def ensure_collection(client, collection_name: str) -> None:
    """Ensure ``collection_name`` exists at 1536-dim cosine, self-healing width.

    Uses the qdrant-client 1.x ``collection_exists`` helper instead of
    try/except-on-create. When absent, creates the collection at
    ``EMBEDDING_DIM``/cosine (correcting the scaffold's undersized default).
    When present at the wrong vector width (e.g. a stale 512 collection from a
    prior partial run), deletes and recreates it at 1536 so subsequent upserts
    succeed. When already at 1536, leaves it untouched (no destructive
    recreate).

    Args:
        client: A connected ``QdrantClient``.
        collection_name: Target collection name.
    """
    from qdrant_client.models import Distance, VectorParams

    def _create():
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )

    if not client.collection_exists(collection_name):
        _create()
        logger.info("Created Qdrant collection %s at size=%d/cosine", collection_name, EMBEDDING_DIM)
        return

    current = client.get_collection(collection_name).config.params.vectors.size
    if current != EMBEDDING_DIM:
        logger.warning(
            "Collection %s exists at wrong size=%d; self-healing to %d",
            collection_name, current, EMBEDDING_DIM,
        )
        client.delete_collection(collection_name)
        _create()
    else:
        logger.info("Collection %s already at size=%d/cosine", collection_name, EMBEDDING_DIM)


def run_pipeline(sources: str = "all", clear_qdrant: bool = False):
    """
    Run the full dlt-based ingestion pipeline.

    Args:
        sources: Comma-separated source names or "all"
        clear_qdrant: If True, clear Qdrant collection before loading
    """
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        logger.error("Required packages not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("SECURITY RAG INGESTION PIPELINE")
    logger.info("=" * 60)

    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
    collection_name = os.getenv("QDRANT_COLLECTION_NAME", "security_rag")

    try:
        client = QdrantClient(host=qdrant_host, port=qdrant_port)
        logger.info("Connected to Qdrant at %s:%s", qdrant_host, qdrant_port)
    except Exception as e:
        logger.error("Failed to connect to Qdrant: %s", e)
        sys.exit(1)

    if clear_qdrant:
        try:
            client.delete_collection(collection_name)
            logger.info("Cleared Qdrant collection: %s", collection_name)
        except Exception as e:
            logger.warning("Collection clear failed (may not exist): %s", e)

    ensure_collection(client, collection_name)

    # Stage 1 + Stage 2 wiring lands in Task 2.
    raise NotImplementedError("two-stage flow implemented in Task 2")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run security RAG ingestion pipeline")
    parser.add_argument("--sources", default="all", help="Comma-separated sources or 'all'")
    parser.add_argument("--clear-qdrant", action="store_true", help="Clear Qdrant before loading")

    args = parser.parse_args()
    run_pipeline(sources=args.sources, clear_qdrant=args.clear_qdrant)
