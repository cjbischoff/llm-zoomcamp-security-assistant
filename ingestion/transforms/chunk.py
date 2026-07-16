"""Chunking logic for security documents."""

import re
from typing import List, Dict, Any

import tiktoken

# text-embedding-3-small uses the cl100k_base tokenizer family. Loaded once at
# import so cap_by_tokens is cheap to call per section.
_ENC = tiktoken.get_encoding("cl100k_base")


def cap_by_tokens(text: str, max_tokens: int = 512, overlap: int = 50) -> List[str]:
    """Split text into pieces bounded by a real token count.

    Args:
        text: The text to cap.
        max_tokens: Maximum tokens per emitted piece.
        overlap: Tokens shared between consecutive pieces (context continuity).

    Returns:
        ``[text]`` when the encoded length is within the cap; otherwise a list
        of decoded windows, each within ``max_tokens``, advancing by
        ``max_tokens - overlap`` tokens.
    """
    toks = _ENC.encode(text)
    if len(toks) <= max_tokens:
        return [text]
    step = max_tokens - overlap
    return [_ENC.decode(toks[s:s + max_tokens]) for s in range(0, len(toks), step)]


class Chunker:
    """Source-specific chunking logic."""

    @staticmethod
    def chunk_owasp_threat(text: str, threat_id: str, threat_name: str) -> List[Dict[str, Any]]:
        """Emit one chunk per OWASP threat entry, token-capped.

        Args:
            text: The threat entry body.
            threat_id: Canonical threat id (e.g. ``LLM01``).
            threat_name: Human-readable threat name.

        Returns:
            List of ``{"text", "metadata"}`` chunks. Normally one entry (D-03);
            an oversized entry splits into within-cap pieces sharing metadata.
        """
        return [
            {
                "text": piece,
                "metadata": {
                    "source": "owasp",
                    "threat_id": threat_id,
                    "threat_name": threat_name,
                    "chunk_type": "threat_entry",
                },
            }
            for piece in cap_by_tokens(text)
        ]

    @staticmethod
    def chunk_by_sections(text: str, source: str, section_title: str = None) -> List[Dict[str, Any]]:
        """Chunk text on markdown headings, token-capping each section.

        Args:
            text: Raw markdown/mdx text (no MD->HTML conversion).
            source: Source identifier preserved on every chunk.
            section_title: Optional title applied to emitted chunks.

        Returns:
            List of ``{"text", "metadata"}`` chunks, one per within-cap section
            piece, each carrying source and section metadata (D-04).
        """
        sections = re.split(r'(?:^|\n)#+\s+', text)

        chunks = []
        for i, section in enumerate(sections):
            if len(section.split()) < 30:  # Skip very short sections
                continue
            for piece in cap_by_tokens(section):
                chunks.append({
                    "text": piece,
                    "metadata": {
                        "source": source,
                        "section_index": i,
                        "section_title": section_title or f"Section {i}",
                        "chunk_type": "section",
                    },
                })

        return chunks

    @staticmethod
    def chunk_generic(text: str, source: str, filename: str = None) -> List[Dict[str, Any]]:
        """Chunk an arbitrary document, token-capping oversized text.

        Args:
            text: The document body.
            source: Source identifier preserved on every chunk.
            filename: Optional filename recorded in metadata.

        Returns:
            List of ``{"text", "metadata"}`` chunks, one per within-cap piece.
        """
        return [
            {
                "text": piece,
                "metadata": {
                    "source": source,
                    "filename": filename or "unknown",
                    "chunk_type": "document",
                },
            }
            for piece in cap_by_tokens(text)
        ]
