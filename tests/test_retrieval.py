"""RED contract for DenseRetriever dense search + failure modes (RET-01/RET-02).

Unit tests, no network. ``rag.retrieval.QdrantClient`` is mocked; the target
``DenseRetriever`` import is deferred INTO each test body so the not-yet-real
shape fails RED (assertion/attribute), never at collection time.

Contracts encoded:
  * RET-01: ``query_points().points[i].score/.payload`` map to
    ``{"text", "score", "metadata"}`` hits, score copied verbatim (cosine, no
    inversion), ``text`` excluded from ``metadata``; the retriever returns
    ``{"status": "ok", "hits": [...]}``.
  * RET-02 / D-03: ``collection_exists`` False → ``collection_missing`` (not a
    silent ``[]``); ``ResponseHandlingException`` → ``backend_down``;
    ``UnexpectedResponse`` from ``query_points`` → backend error; a genuine
    empty ``.points`` with the collection present → ``ok`` + ``hits == []``
    (empty is NOT an error).

RED until Plan 02-02 migrates ``search`` → ``query_points`` and adds the status
channel. The scaffold still calls the removed ``.search`` and returns a bare
list, so these tests fail for the right reason before implementation.
"""


def _mock_qdrant(mocker, *, exists=True, exists_exc=None, query_exc=None, points=None):
    """Patch ``rag.retrieval.QdrantClient`` and script its behavior.

    Args:
        mocker: pytest-mock fixture.
        exists: Return value of ``collection_exists`` (when it does not raise).
        exists_exc: Exception instance to raise from ``collection_exists``.
        query_exc: Exception instance to raise from ``query_points``.
        points: List of ``ScoredPoint``-like mocks for ``query_points().points``.

    Returns:
        The mocked client instance (its calls are recorded).
    """
    client = mocker.MagicMock()

    if exists_exc is not None:
        client.collection_exists.side_effect = exists_exc
    else:
        client.collection_exists.return_value = exists

    if query_exc is not None:
        client.query_points.side_effect = query_exc
    else:
        response = mocker.MagicMock()
        response.points = points if points is not None else []
        client.query_points.return_value = response

    mocker.patch("rag.retrieval.QdrantClient", return_value=client)
    return client


def test_maps_query_points(mocker):
    """A scored point maps to {text, score, metadata} with score verbatim (RET-01)."""
    point = mocker.MagicMock(
        score=0.57,
        payload={
            "text": "Prompt injection manipulates the model via crafted input.",
            "threat_id": "LLM01",
            "source": "owasp_llm_top_10",
        },
    )
    _mock_qdrant(mocker, exists=True, points=[point])

    from rag.retrieval import DenseRetriever

    result = DenseRetriever().retrieve([0.1] * 1536, top_k=5)

    assert result["status"] == "ok"
    assert len(result["hits"]) == 1
    hit = result["hits"][0]
    assert set(hit.keys()) == {"text", "score", "metadata"}
    assert hit["score"] == 0.57  # cosine similarity copied verbatim, no inversion
    assert hit["text"] == "Prompt injection manipulates the model via crafted input."
    assert "text" not in hit["metadata"]  # text lives at the top level, not in metadata
    assert hit["metadata"]["threat_id"] == "LLM01"
    assert hit["metadata"]["source"] == "owasp_llm_top_10"


def test_failure_modes(mocker):
    """collection_missing / backend_down / backend_error / genuine-empty (RET-02, D-03)."""
    from qdrant_client.http.exceptions import (
        ResponseHandlingException,
        UnexpectedResponse,
    )

    # Missing collection -> explicit status, NOT a silent [].
    _mock_qdrant(mocker, exists=False)
    from rag.retrieval import DenseRetriever

    missing = DenseRetriever().retrieve([0.1] * 1536)
    assert missing["status"] == "collection_missing"
    assert missing["hits"] == []

    # Backend down (connection refused / timeout) -> backend_down.
    _mock_qdrant(mocker, exists_exc=ResponseHandlingException("connection refused"))
    down = DenseRetriever().retrieve([0.1] * 1536)
    assert down["status"] == "backend_down"
    assert down["hits"] == []

    # query_points raises 404-style UnexpectedResponse -> a backend error status.
    _mock_qdrant(
        mocker,
        exists=True,
        query_exc=UnexpectedResponse(
            status_code=404, reason_phrase="Not Found", content=b"", headers=None
        ),
    )
    err = DenseRetriever().retrieve([0.1] * 1536)
    assert err["status"] in ("backend_error", "backend_down")
    assert err["hits"] == []

    # Collection present, zero points -> ok + [] (empty is NOT an error).
    _mock_qdrant(mocker, exists=True, points=[])
    empty = DenseRetriever().retrieve([0.1] * 1536)
    assert empty["status"] == "ok"
    assert empty["hits"] == []
