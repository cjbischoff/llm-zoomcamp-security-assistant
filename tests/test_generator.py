"""RED contract for LLMGenerator streaming + prompt variants (GEN-02/GEN-03).

Unit tests, no network. ``rag.generator.AsyncOpenAI`` is mocked so that
``chat.completions.create`` returns an async iterator of chunks (mirroring
openai 2.45). The async generator is drained with the stdlib ``collect_stream``
fixture. Target imports are deferred into each test body.

Contracts encoded:
  * GEN-02: streaming yields multiple incremental chunks whose concatenation is
    the token stream — not a single blob.
  * GEN-02 guard: a chunk with ``choices == []`` (the usage-only final chunk)
    must not raise ``IndexError`` and must contribute no output.
  * GEN-03 / D-06: the practitioner system prompt differs from base and instructs
    inline threat-ID citation plus concrete mitigations.

RED until Plan 02-03: the scaffold indexes ``chunk.choices[0]`` without a guard
(IndexError on the empty chunk, swallowed into an error string) and the
practitioner *system* prompt does not yet instruct citation/mitigations.
"""

TOKENS = ["Prompt ", "injection ", "is ", "[LLM01]."]


def _mock_async_openai(mocker, tokens=TOKENS):
    """Patch ``rag.generator.AsyncOpenAI`` with a streaming chat-completions mock.

    ``create`` is awaited and must return an async iterator. A fresh async
    generator is produced per call (via ``side_effect``) so a test may stream
    more than once. Each stream yields one chunk per token plus a final chunk
    with ``choices == []`` to exercise the empty-choices guard.

    Args:
        mocker: pytest-mock fixture.
        tokens: Token strings to emit as ``choices[0].delta.content``.

    Returns:
        The mocked ``create`` AsyncMock (its ``call_args_list`` records messages).
    """

    def _make_stream(**_kwargs):
        async def _stream():
            for tok in tokens:
                chunk = mocker.MagicMock()
                chunk.choices = [mocker.MagicMock()]
                chunk.choices[0].delta.content = tok
                yield chunk
            # Usage-only final chunk: empty choices must not raise / add output.
            empty = mocker.MagicMock()
            empty.choices = []
            yield empty

        return _stream()

    client = mocker.MagicMock()
    create = mocker.AsyncMock(side_effect=_make_stream)
    client.chat.completions.create = create
    mocker.patch("rag.generator.AsyncOpenAI", return_value=client)
    return create


def test_streams_incrementally(mocker, collect_stream):
    """Output arrives as >1 chunk and joins to exactly the token stream (GEN-02)."""
    _mock_async_openai(mocker)
    from rag.generator import LLMGenerator

    chunks = collect_stream(
        LLMGenerator().stream_answer(query="q", context="ctx", prompt_variant="base")
    )

    assert len(chunks) > 1  # token-by-token, not one blob
    assert "".join(chunks) == "".join(TOKENS)


def test_empty_choices_guard(mocker, collect_stream):
    """The empty-choices chunk contributes no output and raises no IndexError."""
    _mock_async_openai(mocker)
    from rag.generator import LLMGenerator

    chunks = collect_stream(
        LLMGenerator().stream_answer(query="q", context="ctx", prompt_variant="base")
    )

    joined = "".join(chunks)
    assert joined == "".join(TOKENS)  # nothing extra from the empty chunk
    assert "Error generating answer" not in joined  # no swallowed IndexError


def test_variants_differ(mocker, collect_stream):
    """Practitioner system prompt differs from base and mandates cites+mitigations (GEN-03)."""
    create = _mock_async_openai(mocker)
    from rag.generator import LLMGenerator

    gen = LLMGenerator()
    collect_stream(gen.stream_answer(query="q", context="ctx", prompt_variant="base"))
    collect_stream(
        gen.stream_answer(query="q", context="ctx", prompt_variant="practitioner")
    )

    def _system(call):
        return next(m["content"] for m in call.kwargs["messages"] if m["role"] == "system")

    base_sys = _system(create.call_args_list[0])
    prac_sys = _system(create.call_args_list[1])

    assert base_sys != prac_sys
    prac = prac_sys.lower()
    assert "mitigation" in prac  # concrete mitigations (D-06)
    assert "cite" in prac or "citation" in prac  # inline citation instruction
    assert "threat" in prac  # threat-ID citation
