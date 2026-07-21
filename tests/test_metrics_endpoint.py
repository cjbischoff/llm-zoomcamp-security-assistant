"""RED contract for the /metrics endpoint import-bug fix (INT-03/D-04a).

Unit test, no live infra. The lifespan client constructors are patched so
entering the real lifespan builds mocks (not live Qdrant/OpenAI/Postgres). The
endpoint is driven through the ASGI stack with httpx's ``ASGITransport`` on a
stdlib event loop — the project's version-agnostic client idiom (STATE.md: httpx
drift breaks starlette ``TestClient``; ``ASGITransport`` is the workaround).

Contract: GET /metrics returns 200, the Prometheus exposition content-type
(``CONTENT_TYPE_LATEST``), and a body containing the real registered counter
name ``rag_queries_total``.

RED until Wave 2 (05-02): today ``/metrics`` does ``from monitoring.metrics
import MetricsCollector`` — but that class lives in ``monitoring.logging``, so
the import raises and the handler returns 500 (and even on success it would
serialize hardcoded zeros as JSON, wrong content-type). Also ``api.main`` has no
``lifespan`` yet, so the patch targets below do not exist. The plan that turns
this green replaces the handler with ``Response(generate_latest(),
media_type=CONTENT_TYPE_LATEST)``.
"""

import asyncio


def _patch_lifespan_ctors(mocker):
    """Patch the four lifespan client constructors so startup builds mocks."""
    mocker.patch("api.main.QdrantClient")
    mocker.patch("api.main.AsyncOpenAI")
    mocker.patch("api.main.OpenAI")
    mocker.patch("api.main.create_engine")


def test_metrics_returns_prometheus_text(mocker):
    """/metrics: 200 + prometheus content-type + rag_queries_total in body (INT-03)."""
    _patch_lifespan_ctors(mocker)

    import httpx
    from prometheus_client import CONTENT_TYPE_LATEST
    from api.main import app, lifespan

    async def _run():
        async with lifespan(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.get("/metrics")

    resp = asyncio.run(_run())

    assert resp.status_code == 200
    assert resp.headers["content-type"] == CONTENT_TYPE_LATEST
    assert "rag_queries_total" in resp.text
