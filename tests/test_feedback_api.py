"""RED contract for the Pydantic-validated /feedback body (INT-02 / Security V5).

Unit test, no live infra. The lifespan client constructors are patched so the
real lifespan builds mocks, and ``QueryLogger.log_feedback`` is patched to a
no-op so a valid POST never touches Postgres. Driven through the ASGI stack with
httpx's ``ASGITransport`` (the project's version-agnostic client idiom).

Contract: /feedback accepts a JSON body ``{query_id, rating}`` where ``rating``
is bound to ``Literal[-1, 1]`` (thumbs). A valid thumbs body → 200; an
out-of-range rating (5) → 422; a missing ``query_id`` → 422 — Pydantic rejects
at the trust boundary before the handler body (Security V5).

RED until Wave 2 (05-02): today ``/feedback`` takes ``query_id``/``feedback`` as
QUERY PARAMS (not a JSON body), so a JSON body is rejected as missing params and
the valid-thumbs case never returns 200; ``api.main`` also has no ``lifespan``.
The plan that turns this green replaces the signature with a ``FeedbackRequest``
Pydantic body carrying ``rating: Literal[-1, 1]``.
"""

import asyncio


def _patch_lifespan_ctors(mocker):
    """Patch the four lifespan client constructors so startup builds mocks."""
    mocker.patch("api.main.QdrantClient")
    mocker.patch("api.main.AsyncOpenAI")
    mocker.patch("api.main.OpenAI")
    mocker.patch("api.main.create_engine")


def _post_feedback(mocker, body):
    """POST a JSON body to /feedback through the ASGI stack; return the response."""
    _patch_lifespan_ctors(mocker)
    mocker.patch("monitoring.logging.QueryLogger.log_feedback", return_value=None)

    import httpx
    from api.main import app, lifespan

    async def _run():
        async with lifespan(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.post("/feedback", json=body)

    return asyncio.run(_run())


def test_valid_thumbs_accepted(mocker):
    """A valid {query_id, rating: 1} body persists and returns 200 (INT-02)."""
    resp = _post_feedback(mocker, {"query_id": "abc", "rating": 1})
    assert resp.status_code == 200


def test_out_of_range_rating_rejected(mocker):
    """rating=5 is outside Literal[-1, 1] → 422 at the boundary (Security V5)."""
    resp = _post_feedback(mocker, {"query_id": "abc", "rating": 5})
    assert resp.status_code == 422


def test_missing_query_id_rejected(mocker):
    """A body missing query_id → 422 before the handler body (Security V5)."""
    resp = _post_feedback(mocker, {"rating": 1})
    assert resp.status_code == 422
