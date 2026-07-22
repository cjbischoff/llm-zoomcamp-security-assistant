"""dlt source for the NIST Generative AI Profile (NIST.AI.600-1) PDF."""

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

PDF_URL = "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf"
# Numbered section headings, e.g. "2.1 CBRN Information" — used to split the
# extracted text into sections. Downstream the Chunker token-caps each section.
_HEADING = re.compile(r"(?m)^\s*(\d+(?:\.\d+)*)\s+[A-Z].{0,80}$")


@dlt.resource(name="nist_ai_rmf", write_disposition="merge", primary_key="doc_id")
def fetch_nist_ai_rmf() -> Generator[dict, None, None]:
    """Download the NIST GenAI Profile PDF and yield one row per section.

    Fetches ``NIST.AI.600-1.pdf``, extracts text with pypdf, and splits it on
    numbered section headings. Sections are emitted whole (no character
    truncation); the Stage 2 Chunker applies the token cap.

    Yields:
        dict: A row with ``doc_id``, ``section_index``, ``content``,
        ``source``, ``url``, ``total_pages``, and ``fetched_at``.

    Notes:
        On download/parse failure this logs a warning and yields nothing
        (continue-and-report). The temp PDF file is always removed.
    """
    try:
        response = requests.get(PDF_URL, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Source nist_ai_rmf download failed, skipping: %s", e)
        return

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(response.content)
        pdf_path = tmp.name

    try:
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

        # Split on numbered headings; fall back to the whole doc if none match.
        boundaries = [m.start() for m in _HEADING.finditer(full_text)]
        if boundaries:
            spans = boundaries + [len(full_text)]
            sections = [full_text[spans[i] : spans[i + 1]] for i in range(len(boundaries))]
        else:
            sections = [full_text]

        for i, section_text in enumerate(sections):
            if len(section_text.split()) < 50:  # skip heading-only fragments
                continue
            yield {
                "doc_id": f"nist_ai_rmf::{i}",
                "section_index": i,
                "content": section_text.strip(),
                "source": "nist_ai_rmf",
                "url": PDF_URL,
                "total_pages": total_pages,
                "fetched_at": datetime.now(timezone.utc),
            }
    except Exception as e:  # noqa: BLE001 - continue-and-report
        logger.warning("Source nist_ai_rmf parse failed, skipping: %s", e)
        return
    finally:
        Path(pdf_path).unlink(missing_ok=True)


@dlt.source
def nist_ai_rmf_source():
    """dlt source definition for the NIST GenAI Profile."""
    return [fetch_nist_ai_rmf()]
