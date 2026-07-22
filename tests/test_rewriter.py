"""RED contract for the rebuilt threat-ID rewriter (BON-02, D-02, D-03; SC4).

Pure-unit, ``re``-only. The target ``QueryRewriter`` is imported INTO each test
body (deferred). These tests fail RED against the current scaffold, whose
``THREAT_MAPPINGS`` carries the stale OWASP LLM-1.0 scheme + ``AGENTIC-0x`` ids
and whose ``rewrite()`` returns a bracket-prefixed *string* rather than the
detected id.

Contracts encoded (RESEARCH §Correctness-Critical Taxonomy + §Pattern 4):
  * ``rewrite(q)`` returns ``(query, threat_id | None)`` — the second element is a
    canonical id string or ``None``, never a rewritten ``"[LLM01] ..."`` string.
  * Verified LLM 2.0 + ASI mappings (supply chain → LLM03, sensitive information
    → LLM02, data poisoning → LLM04, excessive agency → LLM06, prompt injection
    → LLM01, agent goal hijack → ASI01, rogue agents → ASI10).
  * ``"chain of thought"`` is NOT a mapping → ``None`` (no substring leak to LLM03).
  * Longest-match precedence: a query with both "supply chain" and a bare "chain".
  * ``test_no_stale_ids``: every value matches ``^(LLM(0[1-9]|10)|ASI(0[1-9]|10))$``.
"""

import re


def test_ambiguous_terms_map_to_correct_ids():
    """Each verified free-text phrase resolves to its canonical LLM/ASI id."""
    from rag.rewriter import QueryRewriter

    r = QueryRewriter()
    cases = {
        "how do I stop prompt injection attacks": "LLM01",
        "preventing sensitive information leakage": "LLM02",
        "risks in the software supply chain for models": "LLM03",
        "defending against data poisoning": "LLM04",
        "limiting excessive agency in agents": "LLM06",
        "what is agent goal hijack": "ASI01",
        "detecting rogue agents in a fleet": "ASI10",
    }
    for query, expected in cases.items():
        _, tid = r.rewrite(query)
        assert tid == expected, f"{query!r} → {tid!r}, expected {expected!r}"


def test_chain_of_thought_is_not_supply_chain():
    """A phrase containing 'chain' but not 'supply chain' must not map to LLM03."""
    from rag.rewriter import QueryRewriter

    _, tid = QueryRewriter().rewrite("walk me through the chain of thought reasoning")
    assert tid is None


def test_longest_match_precedence():
    """A query with both 'supply chain' and a bare 'chain' still resolves to LLM03."""
    from rag.rewriter import QueryRewriter

    _, tid = QueryRewriter().rewrite("the supply chain is a long chain of vendors")
    assert tid == "LLM03"


def test_returns_id_or_none_never_a_bracket_string():
    """The second tuple element is a canonical id or None — never a rewritten string."""
    from rag.rewriter import QueryRewriter

    r = QueryRewriter()
    _, hit = r.rewrite("prompt injection")
    assert hit == "LLM01"  # the id, not "[LLM01] prompt injection"

    _, miss = r.rewrite("what time is it")
    assert miss is None


def test_no_stale_ids():
    """Every mapping value is a canonical LLM01-10 / ASI01-10 id (no legacy schemes)."""
    from rag.rewriter import QueryRewriter

    canonical = re.compile(r"^(LLM(0[1-9]|10)|ASI(0[1-9]|10))$")
    for phrase, tid in QueryRewriter.THREAT_MAPPINGS.items():
        assert canonical.match(tid), f"{phrase!r} → stale/invalid id {tid!r}"
