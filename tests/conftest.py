"""Shared pytest fixtures for the Phase 1 ingestion test suite.

The live-Qdrant fixtures skip (never error) when Qdrant is unreachable so the
pure-logic tests still run in a bare CI environment. qdrant-client is imported
INSIDE the fixture, never at module top, so collection never fails when the
dependency or the service is absent.
"""

import asyncio
import os
import uuid

import pytest


def pytest_configure(config):
    """Register custom markers used by the live probes.

    Args:
        config: The pytest config object.
    """
    config.addinivalue_line(
        "markers", "slow: live probe that may download a model (~80MB) on first run"
    )


@pytest.fixture
def fake_vector():
    """Return a fixed 1536-dim query-embedding stand-in for unit retrieval tests.

    Mirrors the Phase 1 collection contract (text-embedding-3-small → 1536).
    Never 512 — that was the Phase 1 landmine. The value is arbitrary; unit
    tests mock the vector search, so only the length/shape matters.

    Returns:
        list[float]: A ``[0.1] * 1536`` list.
    """
    return [0.1] * 1536


@pytest.fixture
def openai_available():
    """Skip the test unless ``OPENAI_API_KEY`` is present in the environment.

    Mirrors the ``qdrant_client`` skip style so live generation/embedding tests
    degrade to a skip (never an error) offline. The key's value is only checked
    for presence — it is never printed, logged, or asserted on.

    Returns:
        bool: ``True`` when a key is present (otherwise the test is skipped).
    """
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set — live OpenAI test skipped")
    return True


@pytest.fixture
def fused_hits():
    """Return a small RRF-shaped hit list for reranker/hybrid unit tests.

    Mirrors the post-fusion hit contract: each hit is
    ``{"id", "text", "score", "metadata"}`` where ``score`` is the original
    dense cosine similarity (preserved through fusion for the 0.4 gate) and at
    least one hit carries ``metadata["threat_id"]`` so soft-boost tests have a
    target. Ordered as a plausible pre-rerank fused list.

    Returns:
        list[dict]: Five hit dicts with distinct string ``id`` values.
    """
    return [
        {"id": "id-a", "text": "prompt injection manipulates the model via crafted input",
         "score": 0.61, "metadata": {"threat_id": "LLM01", "source": "owasp_llm_top_10"}},
        {"id": "id-b", "text": "supply chain risk from third-party model dependencies",
         "score": 0.55, "metadata": {"threat_id": "LLM03", "source": "owasp_llm_top_10"}},
        {"id": "id-c", "text": "excessive agency grants an agent too much autonomy",
         "score": 0.48, "metadata": {"threat_id": "LLM06", "source": "owasp_llm_top_10"}},
        {"id": "id-d", "text": "the model context protocol defines a client-server transport",
         "score": 0.44, "metadata": {"source": "mcp_protocol_spec"}},
        {"id": "id-e", "text": "nist ai risk management framework govern map measure manage",
         "score": 0.41, "metadata": {"source": "nist_ai_rmf"}},
    ]


@pytest.fixture
def cross_encoder_available():
    """Skip the test unless ``sentence_transformers`` can be imported.

    Mirrors the ``openai_available`` skip style so live rerank tests degrade to
    a skip (never an error) when the heavy dependency is absent. Presence check
    only — the model itself is not loaded and the network is not touched here.

    Returns:
        bool: ``True`` when the package imports (otherwise the test is skipped).
    """
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        pytest.skip("sentence-transformers not installed — live rerank test skipped")
    return True


@pytest.fixture
def collect_stream():
    """Return a helper that fully drains an async generator into a list.

    Avoids adding an async pytest plugin — only ``pytest`` + ``pytest-mock``
    are installed. The returned callable runs the drain on a fresh event loop
    via stdlib :func:`asyncio.run`, so async-generator serving code can be
    exercised from ordinary synchronous test bodies.

    Returns:
        Callable[[AsyncGenerator], list]: Drains the given async generator and
            returns the yielded chunks in order.
    """

    def _drain(async_gen):
        async def _run():
            return [chunk async for chunk in async_gen]

        return asyncio.run(_run())

    return _drain


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
