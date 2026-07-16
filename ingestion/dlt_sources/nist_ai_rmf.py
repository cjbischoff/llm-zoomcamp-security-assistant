"""dlt source for NIST AI Risk Management Framework PDF"""

import dlt
import requests
import tempfile
from pathlib import Path
from PyPDF2 import PdfReader
from typing import Generator


@dlt.resource(name="nist_ai_rmf", write_disposition="replace")
def fetch_nist_ai_rmf() -> Generator[dict, None, None]:
    """
    Download NIST AI Risk Management Framework PDF and extract text.

    Chunks by section heading (~500 tokens per chunk).
    """
    pdf_url = "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf"

    try:
        response = requests.get(pdf_url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Warning: Could not download NIST AI RMF: {e}")
        return

    # Save PDF temporarily and extract text
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(response.content)
        pdf_path = tmp.name

    try:
        reader = PdfReader(pdf_path)
        full_text = ""

        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            full_text += f"\n--- Page {page_num + 1} ---\n{text}"

        # Split by major sections (GOVERN, MAP, MEASURE, MANAGE)
        sections = full_text.split("SECTION")

        for i, section_text in enumerate(sections):
            if len(section_text.split()) < 50:  # Skip short fragments
                continue

            # Truncate to reasonable size
            section_text = section_text[:5000]

            yield {
                "section_index": i,
                "content": section_text,
                "source": "nist_ai_rmf",
                "url": pdf_url,
                "total_pages": len(reader.pages),
                "fetched_at": dlt.current.run_started_at,
            }
    finally:
        Path(pdf_path).unlink()


@dlt.source
def nist_ai_rmf_source():
    """dlt source definition for NIST AI RMF"""
    return [fetch_nist_ai_rmf()]
