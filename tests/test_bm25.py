"""RED contract for the BM25 keyword leg (RET-03).

Unit test over a tiny in-memory corpus using the installed ``rank-bm25`` — no
network, no Qdrant. The target ``BM25Retriever`` is imported INTO each test body
(deferred) so the not-yet-real constructor signature (it currently takes no
corpus and ``retrieve`` returns ``[]``) fails RED cleanly, never at collection.

Contracts encoded (RESEARCH §Pattern 1):
  * ``BM25Retriever`` is constructed over an injected corpus of
    ``{"id","text","metadata"}`` docs (in-memory; no scroll in unit tests).
  * An exact-token query ranks the doc containing that token first.
  * A paraphrase lacking the token ranks a DIFFERENT doc first (orderings differ).
  * Returned hits are shaped ``{"id","text","score","metadata"}``.
  * The query tokenizer matches the index tokenizer (a shared token → score > 0).
"""


def _corpus():
    """Four distinct docs with non-overlapping keyword signatures."""
    return [
        {"id": "c1", "text": "prompt injection manipulates the model with crafted input",
         "metadata": {"threat_id": "LLM01"}},
        {"id": "c2", "text": "supply chain risk from third party dependencies",
         "metadata": {"threat_id": "LLM03"}},
        {"id": "c3", "text": "excessive agency gives an agent too much autonomy",
         "metadata": {"threat_id": "LLM06"}},
        {"id": "c4", "text": "unbounded consumption exhausts compute and quota resources",
         "metadata": {"threat_id": "LLM10"}},
    ]


def test_exact_token_query_ranks_its_doc_first():
    """A literal keyword surfaces the doc that contains it at rank 1."""
    from rag.retrieval import BM25Retriever

    r = BM25Retriever(_corpus())
    hits = r.retrieve("supply chain", top_k=4)
    assert hits[0]["id"] == "c2"


def test_paraphrase_ranks_differently():
    """A query with a different keyword ranks a different doc first (orderings differ)."""
    from rag.retrieval import BM25Retriever

    r = BM25Retriever(_corpus())
    supply = r.retrieve("supply chain", top_k=4)
    consumption = r.retrieve("unbounded consumption", top_k=4)
    assert supply[0]["id"] != consumption[0]["id"]
    assert consumption[0]["id"] == "c4"


def test_hit_shape():
    """Returned hits carry id/text/score/metadata."""
    from rag.retrieval import BM25Retriever

    r = BM25Retriever(_corpus())
    hit = r.retrieve("prompt injection", top_k=1)[0]
    assert set(hit.keys()) >= {"id", "text", "score", "metadata"}
    assert hit["id"] == "c1"
    assert hit["metadata"]["threat_id"] == "LLM01"


def test_tokenizer_alignment_gives_positive_score():
    """A query token shared with the index yields a strictly positive score."""
    from rag.retrieval import BM25Retriever

    r = BM25Retriever(_corpus())
    top = r.retrieve("injection", top_k=1)[0]
    assert top["score"] > 0  # index and query tokenizers agree (Pitfall 4)
