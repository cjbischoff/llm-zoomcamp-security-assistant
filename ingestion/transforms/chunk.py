"""Chunking logic for security documents"""

import re
from typing import List, Dict, Any
import markdown


class Chunker:
    """Source-specific chunking logic"""

    @staticmethod
    def chunk_owasp_threat(text: str, threat_id: str, threat_name: str) -> List[Dict[str, Any]]:
        """
        One chunk per OWASP threat entry.
        Returns: list of {text, metadata}
        """
        # For OWASP threats, keep as single chunk (already well-bounded)
        return [{
            "text": text,
            "metadata": {
                "source": "owasp",
                "threat_id": threat_id,
                "threat_name": threat_name,
                "chunk_type": "threat_entry"
            }
        }]

    @staticmethod
    def chunk_by_sections(text: str, source: str, section_title: str = None) -> List[Dict[str, Any]]:
        """
        Chunk by section headers (~500 tokens per chunk with overlap).
        """
        # Remove markdown
        text = markdown.markdown(text, output_format='html')

        # Split by headers
        sections = re.split(r'(?:^|\n)#+\s+', text)

        chunks = []
        for i, section in enumerate(sections):
            if len(section.split()) < 30:  # Skip very short sections
                continue

            chunks.append({
                "text": section[:2000],  # Cap at 2000 chars for safety
                "metadata": {
                    "source": source,
                    "section_index": i,
                    "section_title": section_title or f"Section {i}",
                    "chunk_type": "section"
                }
            })

        return chunks

    @staticmethod
    def chunk_generic(text: str, source: str, filename: str = None) -> List[Dict[str, Any]]:
        """
        Generic chunking: treat whole document as single chunk.
        """
        return [{
            "text": text[:5000],  # Cap at 5000 chars
            "metadata": {
                "source": source,
                "filename": filename or "unknown",
                "chunk_type": "document"
            }
        }]
