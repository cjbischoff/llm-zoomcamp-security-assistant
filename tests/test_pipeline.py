"""RED contract for RAGPipeline grounding gate + status surfacing (GEN-01/D-02/D-03).

Unit tests, no network. The pipeline is built with its external constructors
(QdrantClient / AsyncOpenAI / embedder OpenAI) patched, then its ``embedder``,
``retriever``, ``generator``, and ``logger`` attributes are replaced with mocks.
The async output is drained with the stdlib ``collect_stream`` fixture. Target
imports are deferred into the test body.

Contracts encoded:
  * GEN-01 / D-02: top-hit cosine score < 0.4 → fixed refusal message AND the
    generator is NOT called (deterministic gate, LLM never invoked).
  * D-04: above threshold → generator is called with a context block carrying
    the hit's bracketed ``[threat_id]``.
  * D-03: ``backend_down`` and ``collection_missing`` each yield a distinct fixed
    message and skip generation (no silent []).

RED until Plan 02-04: the scaffold hardcodes ``retrieval_results = []``, ignores
the retriever status, and always calls the generator.
"""


def _agen(*_args, **_kwargs):
    """Return a fresh single-token async generator standing in for the LLM."""

    async def _stream():
        yield "MODEL ANSWER"

    return _stream()


def _build_pipeline(mocker, *, status="ok", hits=None):
    """Construct RAGPipeline with patched constructors and mocked collaborators.

    Args:
        mocker: pytest-mock fixture.
        status: Retriever status to return.
        hits: Retriever hits list to return.

    Returns:
        tuple: (pipeline, generator_mock) — generator_mock.stream_answer records
            whether generation was invoked and with what context.
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
    retriever.retrieve.return_value = {"status": status, "hits": hits or []}
    pipeline.retriever = retriever

    generator = mocker.MagicMock()
    generator.stream_answer.side_effect = _agen
    pipeline.generator = generator

    pipeline.logger = mocker.MagicMock()
    return pipeline, generator


def test_refuse_below_threshold(mocker, collect_stream):
    """Top hit < 0.4 → refusal, generator never invoked (GEN-01/D-02)."""
    hits = [{"text": "weakly related", "score": 0.25, "metadata": {}}]
    pipeline, generator = _build_pipeline(mocker, status="ok", hits=hits)

    out = "".join(collect_stream(pipeline.stream_answer(query="cookies?", retrieval_mode="dense")))

    assert "indexed sources" in out.lower()  # fixed refusal message
    generator.stream_answer.assert_not_called()  # deterministic gate, no LLM call


def test_answers_above_threshold(mocker, collect_stream):
    """Top hit >= 0.4 → generator called with a bracketed [threat_id] context (D-04)."""
    hits = [
        {
            "text": "Prompt injection manipulates the model.",
            "score": 0.57,
            "metadata": {"threat_id": "LLM01", "source": "owasp_llm_top_10"},
        }
    ]
    pipeline, generator = _build_pipeline(mocker, status="ok", hits=hits)

    out = "".join(collect_stream(
        pipeline.stream_answer(query="what is prompt injection?", retrieval_mode="dense")
    ))

    assert out == "MODEL ANSWER"
    generator.stream_answer.assert_called_once()
    context = generator.stream_answer.call_args.kwargs["context"]
    assert "[LLM01]" in context  # citation-ready block


def test_status_surfacing(mocker, collect_stream):
    """backend_down and collection_missing yield distinct messages, skip generation (D-03)."""
    pipeline_down, gen_down = _build_pipeline(mocker, status="backend_down", hits=[])
    down = "".join(collect_stream(pipeline_down.stream_answer(query="q", retrieval_mode="dense")))

    pipeline_missing, gen_missing = _build_pipeline(
        mocker, status="collection_missing", hits=[]
    )
    missing = "".join(collect_stream(
        pipeline_missing.stream_answer(query="q", retrieval_mode="dense")
    ))

    gen_down.stream_answer.assert_not_called()
    gen_missing.stream_answer.assert_not_called()
    assert down != missing  # distinct failure messages (D-03)
    assert "unavailable" in down.lower()  # backend-down cue
    assert "collection" in missing.lower()  # missing-collection cue
