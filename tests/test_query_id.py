"""RED contract for the X-Query-Id header carrier + threading (D-02a).

Unit test, no live infra. The lifespan client constructors are patched so the
real lifespan builds mocks, and ``rag.pipeline.RAGPipeline`` is patched with a
fake whose ``stream_answer`` yields fixed tokens and records its kwargs. Driven
through the ASGI stack with httpx's ``ASGITransport`` (the project's
version-agnostic client idiom).

Contract: POST /query returns an ``X-Query-Id`` response header whose value is a
non-empty uuid-shaped string, and that SAME value is threaded into
``pipeline.stream_answer(query_id=...)`` — so the persisted query row and any
later feedback row share one id.

RED until Wave 2/3 (05-02/05-03): today ``/query`` returns a bare
``StreamingResponse`` with no ``X-Query-Id`` header and does not generate or
thread a ``query_id``; ``api.main`` also has no ``lifespan``. The plan that turns
this green mints a uuid per request, rides it on the response header, and passes
it into ``stream_answer``.
"""

import asyncio
import uuid


def _patch_lifespan_ctors(mocker):
    """Patch the four lifespan client constructors so startup builds mocks."""
    mocker.patch("api.main.QdrantClient")
    mocker.patch("api.main.AsyncOpenAI")
    mocker.patch("api.main.OpenAI")
    mocker.patch("api.main.create_engine")


def test_query_id_header_present_and_threaded(mocker):
    """/query rides a uuid X-Query-Id header and threads the same id into the pipeline (D-02a)."""
    _patch_lifespan_ctors(mocker)

    recorded = {}

    def _stream_answer(**kwargs):
        recorded.update(kwargs)

        async def _gen():
            yield "prompt "
            yield "injection"

        return _gen()

    fake_pipeline = mocker.MagicMock()
    fake_pipeline.stream_answer.side_effect = _stream_answer
    mocker.patch("rag.pipeline.RAGPipeline", return_value=fake_pipeline)

    import httpx
    from api.main import app, lifespan

    async def _run():
        async with lifespan(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.post("/query", json={"query": "what is prompt injection?"})

    resp = asyncio.run(_run())

    assert resp.status_code == 200
    header_id = resp.headers.get("x-query-id")
    assert header_id  # non-empty
    uuid.UUID(header_id)  # uuid-shaped (raises ValueError if not)
    assert resp.content  # tokens streamed
    # The header id is the SAME id threaded into the pipeline.
    assert recorded.get("query_id") == header_id
