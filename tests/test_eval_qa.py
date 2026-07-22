"""Pure-unit RED spec for ground-truth generation (EVL-01).

Two load-bearing behaviors, both offline (no Qdrant, no OpenAI network):

  1. Determinism — ``evaluation.generate_qa._group_and_sample`` (new symbol,
     Plan 04-02) must seeded-sample per source reproducibly, respect the
     per-source cap, and preserve each chunk's ``id`` / ``source``. Deferred
     import -> RED on the absent symbol now.

  2. Relevance-join guard (Research Pitfall 1 backstop) — the produced row's
     ``chunk_id`` must be the REAL Qdrant point id (a uuid5 string carried on the
     sampled chunk), NOT an enumeration index and NOT whatever the LLM happens to
     echo. The OpenAI client is mocked (no network); the canned completion omits
     ``chunk_id`` on purpose, so the harness must code-stamp the real point id.

RED until Plan 04-02 replaces the ``data/chunks.json`` read + ``chunk_id=i`` with
a Qdrant-scroll sampler that stores the real point id as the join key.
"""


def test_group_and_sample_is_deterministic_and_capped():
    """Seeded per-source sampling is reproducible, capped, and preserves id/source."""
    from evaluation.generate_qa import _group_and_sample

    by_source = {
        "owasp_llm_top_10": [
            {"id": "u1", "text": "t1", "source": "owasp_llm_top_10"},
            {"id": "u2", "text": "t2", "source": "owasp_llm_top_10"},
            {"id": "u3", "text": "t3", "source": "owasp_llm_top_10"},
            {"id": "u4", "text": "t4", "source": "owasp_llm_top_10"},
        ],
        "nist_ai_rmf": [
            {"id": "n1", "text": "t5", "source": "nist_ai_rmf"},
            {"id": "n2", "text": "t6", "source": "nist_ai_rmf"},
            {"id": "n3", "text": "t7", "source": "nist_ai_rmf"},
        ],
    }

    first = _group_and_sample(by_source, per_source=2, seed=42)
    second = _group_and_sample(by_source, per_source=2, seed=42)

    # Deterministic across identical seeds.
    assert [c["id"] for c in first] == [c["id"] for c in second]

    # Per-source cap respected: at most 2 per source, both sources represented.
    from collections import Counter
    counts = Counter(c["source"] for c in first)
    assert counts["owasp_llm_top_10"] == 2
    assert counts["nist_ai_rmf"] == 2

    # Original id/source fields preserved on every returned chunk.
    for chunk in first:
        assert "id" in chunk and "source" in chunk


def test_generated_row_chunk_id_is_real_point_id(mocker):
    """The row's chunk_id is the injected uuid5 point id, never an index or LLM echo."""
    mocker.patch("evaluation.generate_qa.OpenAI")

    from evaluation.generate_qa import QAGenerator

    real_point_id = "3f2c9a4e-8b1d-5c6a-9e0f-1a2b3c4d5e6f"  # uuid5 shape

    generator = QAGenerator()
    # Canned completion: valid Q&A JSON that deliberately omits chunk_id, so the
    # join key can only be correct if the harness code-stamps the real point id.
    canned = mocker.MagicMock()
    canned.choices = [mocker.MagicMock()]
    canned.choices[0].message.content = (
        '[{"question": "What does LLM01 cover?", '
        '"answer": "Prompt injection.", "source": "owasp_llm_top_10"}]'
    )
    generator.client.chat.completions.create.return_value = canned

    rows = generator.generate_qa_for_chunk(
        chunk_text="Prompt injection manipulates the model via crafted input.",
        chunk_id=real_point_id,
        source="owasp_llm_top_10",
    )

    assert rows, "expected at least one generated Q&A row"
    assert rows[0]["chunk_id"] == real_point_id
    assert not isinstance(rows[0]["chunk_id"], int)
