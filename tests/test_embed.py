"""RED contract for the Embedder dimension guarantee (ING-03).

text-embedding-3-small returns 1536-dim vectors natively. The Embedder must
report ``embedding_dim == 1536`` and must NOT pass a narrowing ``dimensions=``
override to the OpenAI API. The OpenAI client is mocked, so no real key or
network is needed.

The target import is deferred into each test body so a missing/incorrect
Embedder produces a FAILURE (RED), not a collection error. RED until Plan
01-02 removes the ``dimensions=512`` intent.
"""

EXPECTED_DIM = 1536


def _mock_openai(mocker, n_vectors):
    """Patch ``ingestion.transforms.embed.OpenAI`` to return fixed 1536-vectors.

    Args:
        mocker: pytest-mock fixture.
        n_vectors: How many embedding rows the mocked response should contain.

    Returns:
        The mocked client instance (its ``embeddings.create`` records calls).
    """
    client = mocker.MagicMock()
    response = mocker.MagicMock()
    response.data = [
        mocker.MagicMock(embedding=[0.0] * EXPECTED_DIM) for _ in range(n_vectors)
    ]
    client.embeddings.create.return_value = response
    mocker.patch("ingestion.transforms.embed.OpenAI", return_value=client)
    return client


def test_embedding_dim_is_1536(mocker):
    """Embedder advertises the native 1536 dimension (not the stale 512)."""
    _mock_openai(mocker, n_vectors=0)
    from ingestion.transforms.embed import Embedder

    assert Embedder().embedding_dim == EXPECTED_DIM


def test_embed_returns_1536_length_vectors(mocker):
    """Every returned vector has length 1536."""
    texts = ["a", "b"]
    _mock_openai(mocker, n_vectors=len(texts))
    from ingestion.transforms.embed import Embedder

    vectors = Embedder().embed(texts)
    assert len(vectors) == len(texts)
    assert all(len(v) == EXPECTED_DIM for v in vectors)


def test_embed_sends_no_dimension_override(mocker):
    """embeddings.create is called with only model + input (no dimensions=)."""
    client = _mock_openai(mocker, n_vectors=1)
    from ingestion.transforms.embed import Embedder

    Embedder().embed(["hello"])
    assert client.embeddings.create.call_count >= 1
    _, kwargs = client.embeddings.create.call_args
    assert set(kwargs.keys()) == {"model", "input"}
