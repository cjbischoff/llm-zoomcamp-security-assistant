"""Query rewriting for threat ID normalization (BONUS FEATURE)"""

from typing import Tuple


class QueryRewriter:
    """Normalize free-text security queries to canonical threat IDs"""

    # Threat ID mappings
    THREAT_MAPPINGS = {
        # LLM Top 10
        "prompt injection": "LLM01",
        "prompt attacks": "LLM01",
        "prompt hijacking": "LLM01",
        "model denial of service": "LLM02",
        "dos": "LLM02",
        "training data poisoning": "LLM03",
        "model poisoning": "LLM03",
        "backdoor": "LLM03",
        "model inversion": "LLM04",
        "supply chain": "LLM05",
        "sensitive info": "LLM06",
        "insecure output": "LLM07",
        "vector db poisoning": "LLM08",
        "plugin security": "LLM09",
        "model theft": "LLM10",
        # Agentic Top 10
        "confused deputy": "AGENTIC-01",
        "tool calling": "AGENTIC-02",
        "agent security": "AGENTIC-03",
        # MCP
        "token expiration": "MCP-security",
        "credential aggregation": "MCP-security",
        "mcp protocol": "MCP",
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
