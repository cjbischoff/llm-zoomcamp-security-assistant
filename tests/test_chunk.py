"""RED contract for the token-cap chunker (ING-02 / D-03, D-04).

The chunker must (1) cap oversized text by TOKEN count into multiple pieces
each within the cap, returning a single piece when under the cap, and (2)
preserve ``source`` and ``threat_id``/``section`` metadata on every emitted
chunk.

Targets are imported inside each test body so a not-yet-implemented helper
produces a FAILURE (RED), never a collection error. RED until Plan 01-02 adds
``cap_by_tokens`` and the tiktoken-based cap.
"""


def test_cap_returns_single_piece_when_under_cap():
    """Short text (under the token cap) comes back as exactly one piece."""
    from ingestion.transforms.chunk import cap_by_tokens

    result = cap_by_tokens("a short sentence", max_tokens=512)
    assert result == ["a short sentence"]


def test_cap_splits_oversized_text_into_multiple_pieces():
    """Text whose token count exceeds the cap splits into >1 piece."""
    from ingestion.transforms.chunk import cap_by_tokens

    big = "word " * 2000  # comfortably over any small cap
    pieces = cap_by_tokens(big, max_tokens=100, overlap=10)
    assert len(pieces) > 1


def test_cap_pieces_each_within_the_cap():
    """Every emitted piece is within the token cap."""
    import tiktoken

    from ingestion.transforms.chunk import cap_by_tokens

    enc = tiktoken.get_encoding("cl100k_base")
    cap = 100
    pieces = cap_by_tokens("word " * 2000, max_tokens=cap, overlap=10)
    assert all(len(enc.encode(p)) <= cap for p in pieces)


def test_chunk_preserves_source_and_threat_id_metadata():
    """Every emitted chunk keeps source + threat_id (D-04 citation metadata)."""
    from ingestion.transforms.chunk import Chunker

    chunks = Chunker.chunk_owasp_threat(
        text="Prompt injection is ...",
        threat_id="LLM01",
        threat_name="Prompt Injection",
    )
    assert chunks, "chunker must emit at least one chunk"
    for chunk in chunks:
        meta = chunk["metadata"]
        assert meta.get("source")
        assert meta.get("threat_id") == "LLM01"
