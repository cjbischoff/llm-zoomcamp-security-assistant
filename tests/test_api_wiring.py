"""RED contract for additive client injection into RAGPipeline (INT-01/D-01).

Unit test, no network. The module-level constructors that the pipeline's
collaborators would otherwise call (``rag.retrieval.QdrantClient``,
``rag.generator.AsyncOpenAI``, ``ingestion.transforms.embed.OpenAI``) are ALL
patched, then ``RAGPipeline`` is built WITH injected client objects. The
contract: when clients are injected, the collaborators use them and do NOT call
their own constructors — i.e. the lifespan-built singletons flow through, no
per-request reconstruction.

RED until Wave 2 (05-02): ``RAGPipeline.__init__`` today takes no arguments, so
``RAGPipeline(qdrant_client=..., aopenai=..., openai=..., engine=...)`` raises
``TypeError``. The plan that turns this green makes the constructor params
additive (default ``None`` → self-construct, preserving every Phase-2/3 test)
and threads each injected client into the matching collaborator.
"""


def test_injected_clients_used_not_reconstructed(mocker):
    """Injected clients flow into collaborators; module ctors are not called (INT-01)."""
    qdrant_ctor = mocker.patch("rag.retrieval.QdrantClient")
    aopenai_ctor = mocker.patch("rag.generator.AsyncOpenAI")
    openai_ctor = mocker.patch("ingestion.transforms.embed.OpenAI")

    from rag.pipeline import RAGPipeline

    qdrant = mocker.MagicMock(name="injected_qdrant")
    aopenai = mocker.MagicMock(name="injected_aopenai")
    openai = mocker.MagicMock(name="injected_openai")
    engine = mocker.MagicMock(name="injected_engine")

    pipeline = RAGPipeline(
        qdrant_client=qdrant, aopenai=aopenai, openai=openai, engine=engine
    )

    # The injected objects were used — the collaborators did not build their own.
    qdrant_ctor.assert_not_called()
    aopenai_ctor.assert_not_called()
    openai_ctor.assert_not_called()

    assert pipeline.retriever.client is qdrant
    assert pipeline.generator.client is aopenai
    assert pipeline.embedder.client is openai
