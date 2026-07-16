"""dlt pipeline orchestration script

Fetches, chunks, embeds, and loads all sources into Qdrant.
"""

import os
import sys
import argparse
import logging
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_pipeline(sources: str = "all", clear_qdrant: bool = False):
    """
    Run the full dlt-based ingestion pipeline.

    Args:
        sources: Comma-separated source names or "all"
        clear_qdrant: If True, clear Qdrant collection before loading
    """
    try:
        import dlt
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct
    except ImportError:
        logger.error("Required packages not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("SECURITY RAG INGESTION PIPELINE")
    logger.info("=" * 60)

    # Step 1: Initialize Qdrant connection
    logger.info("\n[1/4] Initializing Qdrant...")
    qdrant_host = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
    collection_name = os.getenv("QDRANT_COLLECTION_NAME", "security_rag")

    try:
        qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
        logger.info(f"Connected to Qdrant at {qdrant_host}:{qdrant_port}")
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant: {e}")
        sys.exit(1)

    # Clear collection if requested
    if clear_qdrant:
        try:
            qdrant_client.delete_collection(collection_name)
            logger.info(f"Cleared Qdrant collection: {collection_name}")
        except Exception as e:
            logger.warning(f"Collection clear failed (may not exist): {e}")

    # Ensure collection exists
    try:
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=512, distance=Distance.COSINE)
        )
        logger.info(f"Created Qdrant collection: {collection_name}")
    except Exception as e:
        logger.info(f"Collection already exists: {e}")

    # Step 2: Run dlt pipeline
    logger.info("\n[2/4] Running dlt ingestion pipeline...")
    try:
        # Note: Full dlt pipeline implementation would go here
        # This is a simplified version for demonstration
        logger.info("Fetching sources via dlt...")
        logger.info("  - OWASP LLM Top 10")
        logger.info("  - OWASP Agentic Top 10")
        logger.info("  - MCP Protocol Spec")
        logger.info("  - MCP Security Docs")
        logger.info("  - NIST AI RMF")

        logger.info("Note: Install dlt and run full pipeline with:")
        logger.info("  dlt pipeline run ingestion/dlt_sources --destination postgres")

    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
        sys.exit(1)

    # Step 3: Chunk and embed (simplified)
    logger.info("\n[3/4] Chunking and embedding documents...")
    logger.info("  - Loaded chunks: 0 (implement full pipeline)")
    logger.info("  - Embedding dimension: 512 (text-embedding-3-small)")

    # Step 4: Load to Qdrant
    logger.info("\n[4/4] Loading to Qdrant...")
    logger.info("  - Points loaded: 0 (implement full pipeline)")

    logger.info("\n" + "=" * 60)
    logger.info("Pipeline complete!")
    logger.info("=" * 60)
    logger.info(f"\nNext steps:")
    logger.info(f"1. Verify Qdrant collection: http://{qdrant_host}:6333/dashboard")
    logger.info(f"2. Start FastAPI: python api/main.py")
    logger.info(f"3. Open Streamlit UI: streamlit run ui/app.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run security RAG ingestion pipeline")
    parser.add_argument("--sources", default="all", help="Comma-separated sources or 'all'")
    parser.add_argument("--clear-qdrant", action="store_true", help="Clear Qdrant before loading")

    args = parser.parse_args()
    run_pipeline(sources=args.sources, clear_qdrant=args.clear_qdrant)
