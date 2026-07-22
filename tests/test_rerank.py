"""RED contract for cross-encoder rerank + off-loop wrap (BON-03, BON-01, D-05).

Unit tests, no network and no model download. ``test_reorders`` injects a fake
model on the ``Reranker`` so ``CrossEncoder`` is never built; ``test_rerank_off_loop``
patches ``asyncio.to_thread`` and drives the pipeline via the constructor-patch
idiom (analog: ``tests/test_pipeline.py``), draining with ``collect_stream``.

Contracts encoded (RESEARCH §Pattern 3):
  * ``Reranker.rerank(query, fused, top_k)`` reorders via ``self._model.rank`` and
    returns hits carrying a ``rerank_score`` while preserving each hit's cosine
    ``score`` (BON-03).
  * The blocking rerank/hybrid call runs off the event loop through
    ``asyncio.to_thread`` in ``hybrid_rerank`` mode (BON-01).

RED until Plans 03-03 (``Reranker``) and 03-04 (pipeline ``retrieval_mode`` wrap).
"""


def test_reorders(mocker, fused_hits):
    """A model that returns a different rank order reorders the fused hits (BON-03)."""
    # Safety net so a future eager __init__ never downloads a real model; create=True
    # tolerates the seam not existing yet (RED now comes from the Reranker import).
    mocker.patch("rag.retrieval.CrossEncoder", create=True)
    from rag.retrieval import Reranker

    reranker = Reranker()

    fake_model = mocker.MagicMock()
    # Return corpus_ids in an order DIFFERENT from the input fused order.
    fake_model.rank.return_value = [
        {"corpus_id": 2, "score": 9.5},
        {"corpus_id": 0, "score": 8.0},
        {"corpus_id": 4, "score": 6.0},
        {"corpus_id": 1, "score": 4.0},
        {"corpus_id": 3, "score": 2.0},
    ]
    reranker._model = fake_model

    out = reranker.rerank("some query", fused_hits, top_k=5)

    input_ids = [h["id"] for h in fused_hits]
    out_ids = [h["id"] for h in out]
    assert out_ids != input_ids  # order changed
    assert out_ids[0] == fused_hits[2]["id"]  # corpus_id 2 promoted to the top
    for hit in out:
        assert "rerank_score" in hit
        assert "score" in hit  # original cosine preserved (gate is on cosine)


def _build_pipeline(mocker):
    """Construct RAGPipeline with external constructors patched + collaborators mocked.

    Mirrors ``tests/test_pipeline.py::_build_pipeline`` and additionally installs a
    mock ``hybrid`` leg for the ``hybrid_rerank`` path.

    Returns:
        tuple: (pipeline, hybrid_mock).
    """
    mocker.patch("rag.retrieval.QdrantClient")
    mocker.patch("rag.generator.AsyncOpenAI")
    mocker.patch("ingestion.transforms.embed.OpenAI")

    from rag.pipeline import RAGPipeline

    pipeline = RAGPipeline()

    embedder = mocker.MagicMock()
    embedder.embed.return_value = [[0.1] * 1536]
    pipeline.embedder = embedder

    hits = [
        {"id": "h1", "text": "prompt injection", "score": 0.9,
         "metadata": {"threat_id": "LLM01", "source": "owasp_llm_top_10"}},
    ]
    hybrid = mocker.MagicMock()
    hybrid.retrieve.return_value = {"status": "ok", "hits": hits}
    pipeline.hybrid = hybrid

    def _agen(*_a, **_k):
        async def _stream():
            yield "MODEL ANSWER"

        return _stream()

    generator = mocker.MagicMock()
    generator.stream_answer.side_effect = _agen
    pipeline.generator = generator

    pipeline.logger = mocker.MagicMock()
    return pipeline, hybrid


def test_rerank_off_loop(mocker, collect_stream):
    """hybrid_rerank runs the blocking hybrid/rerank call via asyncio.to_thread (BON-01)."""
    async def _passthrough(func, *args, **kwargs):
        return func(*args, **kwargs)

    spy = mocker.patch("rag.pipeline.asyncio.to_thread", side_effect=_passthrough)

    pipeline, hybrid = _build_pipeline(mocker)

    list(collect_stream(
        pipeline.stream_answer(query="what is prompt injection?", retrieval_mode="hybrid_rerank")
    ))

    assert spy.called  # the blocking leg went off the event loop
    # Select the hybrid-retrieve to_thread call specifically (other off-loop calls
    # now include embed + the persistence insert — Phase 5 05-02).
    retrieve_calls = [c for c in spy.call_args_list if c.args and c.args[0] == hybrid.retrieve]
    assert len(retrieve_calls) == 1  # ...and it was the hybrid retrieve
