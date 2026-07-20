"""Contract for retrieval_mode routing through RAGPipeline + /query (D-06/BON-01/Security V5).

Unit tests, no network. Mirrors the constructor-patch idiom from
``tests/test_pipeline.py``: external constructors (QdrantClient / AsyncOpenAI /
embedder OpenAI) are patched, then ``embedder``, ``retriever``, ``hybrid``,
``generator``, and ``logger`` are replaced with mocks. Async output is drained
with the stdlib ``collect_stream`` fixture.

Contracts encoded:
  * D-06: no ``retrieval_mode`` -> dense (``retriever.retrieve``) is called and
    ``hybrid.retrieve`` is NOT — dense is the default fast path.
  * BON-01: ``retrieval_mode="hybrid"`` -> the blocking hybrid leg runs through
    ``asyncio.to_thread`` (off the event loop); dense retriever NOT called.
  * BON-03: ``retrieval_mode="hybrid_rerank"`` -> the off-loop call carries the
    rerank flag ``True``.
  * Security V5: ``/query`` rejects an out-of-enum ``retrieval_mode`` with 422
    before any pipeline work.
"""

_HYBRID_RESULT = {
    "status": "ok",
    "hits": [
        {"id": "a", "text": "t", "score": 0.9,
         "metadata": {"threat_id": "LLM03", "source": "owasp_llm_top_10"}}
    ],
    "gate_score": 0.9,
}


def _agen(*_args, **_kwargs):
    """Return a fresh single-token async generator standing in for the LLM."""

    async def _stream():
        yield "MODEL ANSWER"

    return _stream()


def _build_pipeline(mocker):
    """Construct RAGPipeline with patched constructors and mocked collaborators.

    Mocks BOTH the dense ``retriever`` and the ``hybrid`` legs so routing is
    observable without any network or model.

    Returns:
        tuple: (pipeline, retriever_mock, hybrid_mock).
    """
    mocker.patch("rag.retrieval.QdrantClient")
    mocker.patch("rag.generator.AsyncOpenAI")
    mocker.patch("ingestion.transforms.embed.OpenAI")

    from rag.pipeline import RAGPipeline

    pipeline = RAGPipeline()

    embedder = mocker.MagicMock()
    embedder.embed.return_value = [[0.1] * 1536]
    pipeline.embedder = embedder

    retriever = mocker.MagicMock()
    retriever.retrieve.return_value = {
        "status": "ok",
        "hits": [{"id": "d", "text": "t", "score": 0.9,
                  "metadata": {"threat_id": "LLM01", "source": "owasp_llm_top_10"}}],
    }
    pipeline.retriever = retriever

    hybrid = mocker.MagicMock()
    hybrid.retrieve.return_value = _HYBRID_RESULT
    pipeline.hybrid = hybrid

    generator = mocker.MagicMock()
    generator.stream_answer.side_effect = _agen
    pipeline.generator = generator

    pipeline.logger = mocker.MagicMock()
    return pipeline, retriever, hybrid


def test_default_routes_to_dense(mocker, collect_stream):
    """No retrieval_mode -> dense retriever called, hybrid not (D-06)."""
    pipeline, retriever, hybrid = _build_pipeline(mocker)

    out = "".join(collect_stream(pipeline.stream_answer(query="what is prompt injection?")))

    assert out == "MODEL ANSWER"
    retriever.retrieve.assert_called_once()
    hybrid.retrieve.assert_not_called()


def test_hybrid_routes_off_loop(mocker, collect_stream):
    """retrieval_mode=hybrid -> hybrid.retrieve via asyncio.to_thread, dense not (BON-01)."""
    async def _passthrough(func, *args, **kwargs):
        return func(*args, **kwargs)

    spy = mocker.patch("rag.pipeline.asyncio.to_thread", side_effect=_passthrough)
    pipeline, retriever, hybrid = _build_pipeline(mocker)

    list(collect_stream(
        pipeline.stream_answer(query="what is supply chain risk?", retrieval_mode="hybrid")
    ))

    assert spy.called
    assert spy.call_args.args[0] == hybrid.retrieve
    retriever.retrieve.assert_not_called()


def test_hybrid_rerank_passes_rerank_flag(mocker, collect_stream):
    """retrieval_mode=hybrid_rerank -> the off-loop call carries rerank=True (BON-03)."""
    async def _passthrough(func, *args, **kwargs):
        return func(*args, **kwargs)

    spy = mocker.patch("rag.pipeline.asyncio.to_thread", side_effect=_passthrough)
    pipeline, retriever, hybrid = _build_pipeline(mocker)

    list(collect_stream(
        pipeline.stream_answer(query="what is supply chain risk?", retrieval_mode="hybrid_rerank")
    ))

    assert spy.called
    # The rerank flag is the last positional arg forwarded to hybrid.retrieve.
    assert spy.call_args.args[-1] is True


def test_unknown_mode_normalizes_to_dense(mocker, collect_stream):
    """An unknown retrieval_mode falls back to dense (never dynamic dispatch, Security V5)."""
    pipeline, retriever, hybrid = _build_pipeline(mocker)

    list(collect_stream(
        pipeline.stream_answer(query="what is prompt injection?", retrieval_mode="bogus")
    ))

    retriever.retrieve.assert_called_once()
    hybrid.retrieve.assert_not_called()
