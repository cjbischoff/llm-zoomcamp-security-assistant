"""Query rewriting for threat ID normalization (BONUS FEATURE)"""

from typing import Tuple


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

    def rewrite(self, query: str) -> Tuple[str, str]:
        """
        Rewrite query if it matches a threat pattern.

        Returns: (original_query, rewritten_query_with_threat_id)
        """
        query_lower = query.lower()

        # Check for threat matches
        for pattern, threat_id in self.THREAT_MAPPINGS.items():
            if pattern in query_lower:
                rewritten = f"[{threat_id}] {query}"
                return query, rewritten

        # No match, return original
        return query, query

    def normalize_threat_id(self, threat_id: str) -> str:
        """Normalize threat ID format (uppercase)"""
        return threat_id.upper().strip()
