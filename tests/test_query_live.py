"""RED live-guarded contract: /query streams real tokens end-to-end (INT-01).

Integration test, live-guarded by ``qdrant_client`` + ``openai_available`` —
skips (never errors) when Qdrant is down or the OpenAI key is absent. Drives the
real lifespan (real clients) and POSTs an in-corpus probe through httpx's
``ASGITransport``; asserts a non-empty streamed body and a present ``X-Query-Id``
header.

RED until Wave 2/3 (05-02/05-03): ``api.main`` has no ``lifespan`` and ``/query``
returns no ``X-Query-Id`` header yet, so the import/header assertion fails (when
infra IS up). Offline, the fixtures skip before any of that runs.
"""

import asyncio


def test_query_streams_tokens_with_query_id(qdrant_client, openai_available):
    """A known in-corpus question streams a non-empty answer and an X-Query-Id header (INT-01)."""
    import httpx
    from api.main import app, lifespan

    async def _run():
        async with lifespan(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test", timeout=60.0
            ) as client:
                return await client.post(
                    "/query",
                    json={"query": "What is prompt injection?", "retrieval_mode": "dense"},
                )

    resp = asyncio.run(_run())

    assert resp.status_code == 200
    assert resp.content  # tokens actually streamed
    assert resp.headers.get("x-query-id")  # id carrier present
