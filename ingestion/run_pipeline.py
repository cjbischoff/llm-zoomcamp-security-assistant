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

    # Lazy heavy imports (kept inside the function so `point_id` /
    # `ensure_collection` stay importable without dlt/openai present).
    import dlt
    from qdrant_client.models import PointStruct

    from ingestion.dlt_sources import (
        owasp_llm_source,
        owasp_agentic_source,
        mcp_spec_source,
        mcp_security_source,
        nist_ai_rmf_source,
    )
    from ingestion.transforms.chunk import Chunker
    from ingestion.transforms.embed import Embedder

    # source key -> (dlt source factory, Postgres staging table name)
    registry = {
        "owasp_llm": (owasp_llm_source, "owasp_llm_top_10"),
        "owasp_agentic": (owasp_agentic_source, "owasp_agentic_top_10"),
        "mcp_spec": (mcp_spec_source, "mcp_protocol_spec"),
        "mcp_security": (mcp_security_source, "mcp_security_docs"),
        "nist": (nist_ai_rmf_source, "nist_ai_rmf"),
    }
    selected = list(registry) if sources == "all" else [s.strip() for s in sources.split(",")]
    unknown = [s for s in selected if s not in registry]
    if unknown:
        logger.error("Unknown source(s): %s (known: %s)", unknown, list(registry))
        sys.exit(1)

    # Stage 1: fetch + normalize the sources into Postgres staging.
    # continue-and-report — a single failing source is dropped; the run only
    # aborts if EVERY selected source fails (D-01/D-02).
    logger.info("\n[Stage 1] Staging %d source(s) via dlt -> Postgres...", len(selected))
    pipeline = dlt.pipeline(
        pipeline_name="security_rag",
        destination="postgres",
        dataset_name="staging",
    )
    succeeded, failed = [], []
    for key in selected:
        factory, _ = registry[key]
        try:
            pipeline.run(factory())
            succeeded.append(key)
            logger.info("  staged: %s", key)
        except Exception as e:  # noqa: BLE001 - continue-and-report
            logger.warning("  source %s failed, skipping: %s", key, e)
            failed.append(key)
    if not succeeded:
        logger.error("All sources failed (%s) — aborting.", failed)
        sys.exit(1)
    if failed:
        logger.warning("Continuing without failed source(s): %s", failed)

    # Stage 2: read staging -> chunk -> embed (1536) -> deterministic upsert.
    logger.info("\n[Stage 2] Chunk + embed staged rows -> Qdrant upsert...")
    embedder = Embedder()
    points = []
    for key in succeeded:
        _, table = registry[key]
        try:
            rows = _read_staging(pipeline, table)
        except Exception as e:  # noqa: BLE001 - a bad table read shouldn't kill the run
            logger.warning("  reading staging table %s failed, skipping: %s", table, e)
            continue

        chunks = _chunk_rows(key, rows, Chunker)
        if not chunks:
            logger.warning("  no chunks produced for %s", key)
            continue

        embedded = embedder.embed_chunks(chunks)
        for position, chunk in enumerate(embedded):
            # Payload carries chunk text + citation metadata ONLY — never a
            # secret (OPENAI_API_KEY / POSTGRES_URL are read from env, never
            # persisted).
            points.append(
                PointStruct(
                    id=point_id(key, position, chunk["text"]),
                    vector=chunk["embedding"],
                    payload={**chunk["metadata"], "text": chunk["text"]},
                )
            )
        logger.info("  %s -> %d chunks", key, len(chunks))

    if points:
        client.upsert(collection_name=collection_name, points=points)

    # ING-06: verify a real non-zero count; never report success on empty.
    count = client.count(collection_name=collection_name, exact=True).count
    logger.info("\nPoints in %s: %d", collection_name, count)
    if count == 0:
        logger.error("Collection is empty after ingestion — failing loud (ING-06).")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Pipeline complete! %d points (%d/%d sources staged).",
                count, len(succeeded), len(selected))
    logger.info("=" * 60)


def _read_staging(pipeline, table: str) -> list:
    """Read all rows of a dlt staging table back as dicts.

    Uses the pipeline's SQL client (psycopg2) rather than pandas so Stage 2 has
    no extra dependency. dlt's internal ``_dlt_*`` bookkeeping columns are kept
    as-is; the chunk dispatcher only reads the content/metadata columns.

    Args:
        pipeline: The dlt pipeline whose destination holds the staging schema.
        table: Staging table name (the dlt resource name).

    Returns:
        A list of column-name -> value dicts, one per staged row.
    """
    with pipeline.sql_client() as sql:
        with sql.execute_query(f"SELECT * FROM {table}") as cursor:
            columns = [c[0] for c in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _chunk_rows(source_key: str, rows: list, chunker) -> list:
    """Route staged rows through the source-appropriate Chunker method.

    OWASP rows chunk per-threat (D-03); spec/PDF rows split on sections (D-04).
    Rows with empty content are skipped.

    Args:
        source_key: The registry key identifying the source.
        rows: Staged rows as dicts (from ``_read_staging``).
        chunker: The ``Chunker`` class.

    Returns:
        A list of ``{"text", "metadata"}`` chunks ready to embed.
    """
    chunks = []
    for row in rows:
        content = (row.get("content") or "").strip()
        if not content:
            continue
        if source_key == "owasp_llm":
            chunks += chunker.chunk_owasp_threat(
                content, row.get("threat_id", ""), row.get("threat_name", "")
            )
        elif source_key == "owasp_agentic":
            threat_id = row.get("threat_id", "")
            chunks += chunker.chunk_owasp_threat(content, threat_id, threat_id)
        elif source_key == "mcp_spec":
            chunks += chunker.chunk_by_sections(content, "mcp_protocol_spec", row.get("section"))
        elif source_key == "mcp_security":
            chunks += chunker.chunk_by_sections(
                content, "mcp_security_docs", row.get("section_title")
            )
        elif source_key == "nist":
            chunks += chunker.chunk_by_sections(content, "nist_ai_rmf")
    return chunks


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run security RAG ingestion pipeline")
    parser.add_argument("--sources", default="all", help="Comma-separated sources or 'all'")
    parser.add_argument("--clear-qdrant", action="store_true", help="Clear Qdrant before loading")

    args = parser.parse_args()
    run_pipeline(sources=args.sources, clear_qdrant=args.clear_qdrant)
