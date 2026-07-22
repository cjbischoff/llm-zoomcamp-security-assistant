"""Query rewriting for threat ID normalization (BONUS FEATURE)"""

import re
from typing import Optional, Tuple


class QueryRewriter:
    """Normalize free-text security queries to canonical threat IDs"""

    # Free-text phrase -> canonical threat id. Verified live against the ingested
    # security_rag collection (OWASP LLM 2.0 = LLM01-LLM10, OWASP Agentic = ASI01-ASI10).
    # Scope is LLM/ASI ids only: MCP/NIST chunks carry threat_id=None and cannot be boosted.
    THREAT_MAPPINGS = {
        # --- OWASP LLM 2.0 ---
        "prompt injection": "LLM01",
        "jailbreak": "LLM01",
        "sensitive information disclosure": "LLM02",
        "sensitive information": "LLM02",
        "data leakage": "LLM02",
        "pii disclosure": "LLM02",
        "supply chain": "LLM03",
        "data and model poisoning": "LLM04",
        "data poisoning": "LLM04",
        "model poisoning": "LLM04",
        "training data poisoning": "LLM04",
        "improper output handling": "LLM05",
        "insecure output handling": "LLM05",
        "excessive agency": "LLM06",
        "system prompt leakage": "LLM07",
        "system prompt leak": "LLM07",
        "vector and embedding weaknesses": "LLM08",
        "embedding weaknesses": "LLM08",
        "misinformation": "LLM09",
        "hallucination": "LLM09",
        "unbounded consumption": "LLM10",
        "denial of service": "LLM10",
        "model dos": "LLM10",
        # --- OWASP Agentic (ASI) ---
        "agent goal hijack": "ASI01",
        "goal hijack": "ASI01",
        "tool misuse": "ASI02",
        "tool exploitation": "ASI02",
        "identity and privilege abuse": "ASI03",
        "privilege abuse": "ASI03",
        "agentic supply chain": "ASI04",
        "unexpected code execution": "ASI05",
        "memory and context poisoning": "ASI06",
        "context poisoning": "ASI06",
        "memory poisoning": "ASI06",
        "insecure inter-agent communication": "ASI07",
        "inter-agent communication": "ASI07",
        "cascading agent failures": "ASI08",
        "cascading failures": "ASI08",
        "human-agent trust exploitation": "ASI09",
        "rogue agents": "ASI10",
        "rogue agent": "ASI10",
    }

    def __init__(self) -> None:
        # Longest-phrase-first precedence (D-03): "supply chain" is tested before any
        # shorter overlapping key, so ambiguous inputs resolve deterministically.
        # Each pattern is a re.escape'd literal wrapped in \b -> word-boundary anchored,
        # linear-time (no backtracking / ReDoS).
        ordered = sorted(
            self.THREAT_MAPPINGS.items(), key=lambda kv: len(kv[0]), reverse=True
        )
        self._compiled = [
            (re.compile(rf"\b{re.escape(pattern)}\b"), threat_id)
            for pattern, threat_id in ordered
        ]

    def rewrite(self, query: str) -> Tuple[str, Optional[str]]:
        """Detect the canonical threat id a free-text query refers to.

        Matches word-boundary-anchored phrases in longest-first order so overlapping
        terms resolve to the correct, distinct id (D-03). The detected id feeds the
        retrieval soft-boost (D-04) downstream.

        Args:
            query: The raw user query.

        Returns:
            ``(original_query, detected_threat_id_or_None)`` — the second element is a
            canonical id string (``LLM01``-``LLM10`` / ``ASI01``-``ASI10``) or ``None``
            when no phrase matches. Never a bracket-prefixed rewritten string.

        Example:
            >>> QueryRewriter().rewrite("how do I stop prompt injection")
            ('how do I stop prompt injection', 'LLM01')
        """
        low = query.lower()
        for rx, threat_id in self._compiled:
            if rx.search(low):
                return query, threat_id
        return query, None

    def normalize_threat_id(self, threat_id: str) -> str:
        """Normalize threat ID format (uppercase)"""
        return threat_id.upper().strip()
