"""Doc-lint guarding README.md honesty (SC2/SC3, REP-03/REP-04).

Fast, offline, stdlib + pytest only — no network, no infra fixtures. These tests
fail if the README drifts from the shipped code: a missing source id, a committed
secret-key literal, or a bonus claim that no longer greps in ``rag/``.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
RAG_DIR = REPO_ROOT / "rag"

SOURCE_IDS = (
    "owasp_llm_top_10",
    "owasp_agentic_top_10",
    "mcp_protocol_spec",
    "mcp_security_docs",
    "nist_ai_rmf",
)

# Anchors the README's bonus claims must trace to under rag/.
BONUS_ANCHORS = ("rrf_fuse", "Reranker", "CrossEncoder", "QueryRewriter")

# OpenAI secret-key pattern: the sk- prefix then a 20+ char key run. The 20-char
# floor means the docs placeholder "sk-..." does NOT match (false-positive guard).
SECRET_KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{20,}")


def _readme_text():
    """Return README.md contents once as text.

    Returns:
        str: The full README.md file contents.
    """
    return README.read_text(encoding="utf-8")


def test_all_five_source_ids_present():
    """Each of the five real source ids appears verbatim in the README."""
    text = _readme_text()
    missing = [sid for sid in SOURCE_IDS if sid not in text]
    assert not missing, f"README missing source ids: {missing}"


def test_no_committed_secret_key():
    """The README contains no live OpenAI secret-key literal.

    The regex requires a 20+ character key run so the ``sk-...`` placeholder used
    in docs does not trigger a false positive.
    """
    text = _readme_text()
    match = SECRET_KEY_RE.search(text)
    assert match is None, f"README contains a secret-key literal: {match.group(0)[:8]}..."


def test_bonus_claims_grep_match_rag():
    """Every claimed-bonus anchor appears somewhere under rag/ (code-backed)."""
    rag_text = "\n".join(p.read_text(encoding="utf-8") for p in RAG_DIR.glob("*.py"))
    missing = [anchor for anchor in BONUS_ANCHORS if anchor not in rag_text]
    assert not missing, f"README claims bonuses not found in rag/: {missing}"
