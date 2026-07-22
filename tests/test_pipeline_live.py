"""Availability-guarded live probes for the grounded pipeline (GEN-01/D-02).

Integration tests against live Qdrant + OpenAI. Guarded by the ``qdrant_client``
and ``openai_available`` fixtures, so they skip (never error) when infra is
absent. The async stream is drained with the stdlib ``collect_stream`` fixture.
Target imports are deferred into the test bodies.

RED until Plans 02-02..02-04: a threat-ID query should stream a grounded answer
citing a bracketed threat ID, and an off-corpus query should refuse.
"""


def test_grounded_answer_cites(qdrant_client, openai_available, collect_stream):
    """A threat-ID query streams >1 chunk and cites a bracketed threat ID (GEN-01/D-04)."""
    from rag.pipeline import RAGPipeline

    chunks = collect_stream(
        RAGPipeline().stream_answer(
            query="What is prompt injection LLM01?", prompt_variant="practitioner"
        )
    )

    assert len(chunks) > 1
    answer = "".join(chunks)
    assert "[" in answer and "]" in answer  # a bracketed threat-ID citation


def test_offcorpus_refuses(qdrant_client, openai_available, collect_stream):
    """An off-corpus query refuses instead of answering from parametric memory (D-02)."""
    from rag.pipeline import RAGPipeline

    answer = "".join(
        collect_stream(
            RAGPipeline().stream_answer(query="best chocolate chip cookie recipe")
        )
    )

    assert "indexed sources" in answer.lower()
