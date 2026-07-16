"""Shared pytest fixtures for the Phase 1 ingestion test suite.

The live-Qdrant fixtures skip (never error) when Qdrant is unreachable so the
pure-logic tests still run in a bare CI environment. qdrant-client is imported
INSIDE the fixture, never at module top, so collection never fails when the
dependency or the service is absent.
"""

import os
import uuid

import pytest


@pytest.fixture
def qdrant_client():
    """Yield a live QdrantClient, skipping the test if Qdrant is unreachable.

    Reads QDRANT_HOST / QDRANT_PORT from the environment (defaults
    localhost:6333). Never writes secrets; never errors when the service is
    down — it calls ``pytest.skip`` instead so the suite degrades gracefully.

    Yields:
        QdrantClient: A connected client whose ``get_collections`` call
            succeeded.
    """
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        pytest.skip("qdrant-client not installed")

    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", "6333"))

    try:
        client = QdrantClient(host=host, port=port, timeout=2.0)
        # Cheap round-trip proves the service is actually up.
        client.get_collections()
    except Exception as exc:  # noqa: BLE001 - any connection error → skip
        pytest.skip(f"Qdrant unreachable at {host}:{port}: {exc}")

    return client


@pytest.fixture
def throwaway_collection(qdrant_client):
    """Provide a unique collection name and delete it on teardown.

    Args:
        qdrant_client: The live-Qdrant fixture (skips if unreachable).

    Yields:
        str: A collection name unique to this test, guaranteed absent at start
            and removed afterwards.
    """
    name = f"test_{uuid.uuid4().hex[:12]}"
    try:
        qdrant_client.delete_collection(name)
    except Exception:  # noqa: BLE001 - fresh name, nothing to delete
        pass

    yield name

    try:
        qdrant_client.delete_collection(name)
    except Exception:  # noqa: BLE001 - best-effort cleanup
        pass
