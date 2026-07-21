"""RED contract for pipeline-driven Prometheus counter increments (MON-02).

Unit test, no network. Uses the ``tests/test_pipeline.py`` idiom: patch the
external constructors, build ``RAGPipeline()``, replace its collaborators with
mocks, drive one successful above-gate dense query through ``collect_stream``.
The contract: the module-level ``rag_queries_total`` counter (labelled by
``retrieval_approach``) increases by exactly 1 for that query.

The counter value is read straight from the default registry via
``REGISTRY.get_sample_value`` before and after — a ``None`` sample (label never
seen yet) is treated as 0.

RED until Wave 2 (05-02): ``RAGPipeline.stream_answer`` today never increments
any Prometheus counter. The plan that turns this green calls
``queries_total.labels(retrieval_approach=mode).inc()`` on each served query.
"""


def _agen(*_args, **_kwargs):
    """Return a fresh single-token async generator standing in for the LLM."""

    async def _stream():
        yield "MODEL ANSWER"

    return _stream()


def _build_pipeline(mocker):
    """Build RAGPipeline with patched ctors and mocked collaborators (dense, above gate)."""
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
        "hits": [
            {
                "text": "Prompt injection manipulates the model.",
                "score": 0.9,
                "metadata": {"threat_id": "LLM01", "source": "owasp_llm_top_10"},
            }
        ],
    }
    pipeline.retriever = retriever

    generator = mocker.MagicMock()
    generator.stream_answer.side_effect = _agen
    pipeline.generator = generator

    pipeline.logger = mocker.MagicMock()
    return pipeline


def test_query_increments_counter(mocker, collect_stream):
    """One successful dense query bumps rag_queries_total{retrieval_approach=dense} by 1 (MON-02)."""
    from prometheus_client import REGISTRY

    pipeline = _build_pipeline(mocker)

    labels = {"retrieval_approach": "dense"}
    before = REGISTRY.get_sample_value("rag_queries_total", labels) or 0.0

    out = "".join(
        collect_stream(pipeline.stream_answer(query="what is prompt injection?", retrieval_mode="dense"))
    )
    assert out == "MODEL ANSWER"  # query actually served (above gate)

    after = REGISTRY.get_sample_value("rag_queries_total", labels) or 0.0
    assert after == before + 1
