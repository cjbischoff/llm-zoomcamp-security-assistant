"""RED contract for HybridRetriever RRF + soft-boost + status (RET-04, D-04, Q3).

Unit test, no network. ``rag.retrieval.QdrantClient`` is patched so construction
never touches Qdrant; the retriever's ``.dense`` and ``.bm25`` legs are then
replaced with mocks so fusion is exercised over fixed, index-aligned inputs. The
target ``HybridRetriever`` is imported INTO each test body (deferred).

Contracts encoded:
  * SC2 / RET-04: hybrid top-5 id order differs from dense top-5 (fusion reorders).
  * ``HybridRetriever.retrieve`` returns ``{"status","hits"}`` (not a bare list).
  * D-04: a ``detected_id`` matching a hit's ``metadata["threat_id"]`` soft-boosts
    that hit's rank (rises) without removing the other hits (not a hard filter).
  * Q3: dense ``status="backend_down"`` propagates to the hybrid result.

RED until Plan 03-03 fills the stub (currently returns ``dense_results[:top_k]``,
a bare list, and takes no ``detected_id``).
"""


def _dense_hits():
    """Dense leg hits A..E in cosine order, each carrying an id (RRF join key)."""
    return [
        {"id": "A", "text": "aaa", "score": 0.90, "metadata": {"threat_id": "LLM01"}},
        {"id": "B", "text": "bbb", "score": 0.80, "metadata": {"threat_id": "LLM02"}},
        {"id": "C", "text": "ccc", "score": 0.70, "metadata": {"threat_id": "LLM03"}},
        {"id": "D", "text": "ddd", "score": 0.60, "metadata": {"threat_id": "LLM06"}},
        {"id": "E", "text": "eee", "score": 0.50, "metadata": {"threat_id": "LLM10"}},
    ]


def _bm25_hits():
    """BM25 leg in a DIFFERENT order, introducing F (absent from dense)."""
    return [
        {"id": "F", "text": "fff", "score": 9.0, "metadata": {"source": "mcp_protocol_spec"}},
        {"id": "C", "text": "ccc", "score": 6.0, "metadata": {"threat_id": "LLM03"}},
        {"id": "A", "text": "aaa", "score": 3.0, "metadata": {"threat_id": "LLM01"}},
    ]


def _build_hybrid(mocker, *, dense_status="ok"):
    """Construct HybridRetriever with QdrantClient patched and legs mocked.

    Args:
        mocker: pytest-mock fixture.
        dense_status: status the mocked dense leg reports.

    Returns:
        The HybridRetriever instance with mock ``.dense`` / ``.bm25``.
    """
    mocker.patch("rag.retrieval.QdrantClient")
    from rag.retrieval import HybridRetriever

    hybrid = HybridRetriever()

    dense = mocker.MagicMock()
    dense.retrieve.return_value = {
        "status": dense_status,
        "hits": _dense_hits() if dense_status == "ok" else [],
    }
    hybrid.dense = dense

    bm25 = mocker.MagicMock()
    bm25.retrieve.return_value = _bm25_hits()
    hybrid.bm25 = bm25

    return hybrid


def test_hybrid_differs_from_dense(mocker):
    """Fused top-5 id order differs from dense top-5, and the shape is {status,hits} (SC2)."""
    hybrid = _build_hybrid(mocker)

    result = hybrid.retrieve([0.1] * 1536, "some query", top_k=5)

    assert set(result.keys()) >= {"status", "hits"}
    hybrid_ids = [h["id"] for h in result["hits"]][:5]
    dense_ids = [h["id"] for h in _dense_hits()][:5]
    assert hybrid_ids != dense_ids  # RRF reordered / injected F


def test_soft_boost_raises_matching_threat_id(mocker):
    """detected_id lifts the matching chunk's rank without dropping the others (D-04)."""
    hybrid = _build_hybrid(mocker)

    base = hybrid.retrieve([0.1] * 1536, "q", top_k=6)
    boosted = hybrid.retrieve([0.1] * 1536, "q", detected_id="LLM06", top_k=6)

    base_ids = [h["id"] for h in base["hits"]]
    boosted_ids = [h["id"] for h in boosted["hits"]]

    # 'D' carries threat_id LLM06; boosting must raise its rank (lower index).
    assert boosted_ids.index("D") < base_ids.index("D")
    # Soft-boost, not hard-filter: the other docs are still present.
    assert set(base_ids) == set(boosted_ids)


def test_propagates_backend_down_status(mocker):
    """A dense outage surfaces as the hybrid status, not a masked empty list (Q3)."""
    hybrid = _build_hybrid(mocker, dense_status="backend_down")

    result = hybrid.retrieve([0.1] * 1536, "q", top_k=5)
    assert result["status"] == "backend_down"
