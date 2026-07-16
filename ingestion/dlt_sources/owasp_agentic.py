"""dlt source for the OWASP Top 10 for Agentic Applications (best-effort PDF).

The official Dec 2025 framework is published as a PDF via genai.owasp.org (no
stable markdown repo) and uses the ``ASI01``-``ASI10`` taxonomy — NOT the
scaffold's ``AGENTIC-01`` scheme. This fetcher stores the source's real ASI
ids. Remapping the rewriter's THREAT_MAPPINGS to ASI ids is a Phase 3
dependency, out of scope here. The download link carries a volatile timestamp
query param, so this fetch is best-effort: any failure logs a warning and
yields nothing (continue-and-report drops Agentic; the other 4 sources still
populate the corpus).
"""

import logging
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import dlt
import requests
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Best-effort: the genai.owasp.org download link is volatile (timestamped).
PDF_URL = "https://genai.owasp.org/download/52117/"
_ASI = re.compile(r"\bASI[- ]?(\d{2})\b")
# Section headings such as "ASI01: Agent Authorization" or numbered headings.
_HEADING = re.compile(r"(?m)^\s*(?:ASI[- ]?\d{2}|\d+(?:\.\d+)*)\s+[A-Z].{0,80}$")


@dlt.resource(name="owasp_agentic_top_10", write_disposition="merge", primary_key="doc_id")
def fetch_owasp_agentic() -> Generator[dict, None, None]:
    """Best-effort fetch of the OWASP Agentic Top 10 PDF, yielding sections.

    Downloads the PDF, extracts text with pypdf, splits on headings, and tags
    each section with the source's real ASI id (``ASI01``..``ASI10``) when one
    is present, else a section id.

    Yields:
        dict: A row with ``doc_id``, ``threat_id`` (ASI id or section id),
        ``content``, ``source``, ``url``, and ``fetched_at``.

    Notes:
        LOW-confidence source: the download URL is volatile. On any failure this
        logs a warning and yields nothing (continue-and-report). The temp PDF
        file is always removed.
    """
    try:
        response = requests.get(PDF_URL, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Source owasp_agentic_top_10 download failed, skipping: %s", e)
        return

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(response.content)
        pdf_path = tmp.name

    try:
        reader = PdfReader(pdf_path)
        full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

        boundaries = [m.start() for m in _HEADING.finditer(full_text)]
        if boundaries:
            spans = boundaries + [len(full_text)]
            sections = [full_text[spans[i] : spans[i + 1]] for i in range(len(boundaries))]
        else:
            sections = [full_text]

        for i, section_text in enumerate(sections):
            if len(section_text.split()) < 50:
                continue
            asi_match = _ASI.search(section_text)
            threat_id = f"ASI{asi_match.group(1)}" if asi_match else f"AGENTIC-SEC-{i}"
            yield {
                "doc_id": f"owasp_agentic::{i}",
                "threat_id": threat_id,
                "content": section_text.strip(),
                "source": "owasp_agentic_top_10",
                "url": PDF_URL,
                "fetched_at": datetime.now(timezone.utc),
            }
    except Exception as e:  # noqa: BLE001 - continue-and-report
        logger.warning("Source owasp_agentic_top_10 parse failed, skipping: %s", e)
        return
    finally:
        Path(pdf_path).unlink(missing_ok=True)


@dlt.source
def owasp_agentic_source():
    """dlt source definition for the OWASP Agentic Top 10."""
    return [fetch_owasp_agentic()]
