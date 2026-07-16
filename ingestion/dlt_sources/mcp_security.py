"""dlt source for the MCP security best-practices doc (repo mdx, not HTML scrape)."""

import logging
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import dlt

logger = logging.getLogger(__name__)

REPO_URL = "https://github.com/modelcontextprotocol/modelcontextprotocol"
# The security doc lives in the MCP repo as .mdx — read it from the clone
# instead of scraping the JS-rendered Mintlify site (which returns sparse text).
SECURITY_DOC = "docs/docs/tutorials/security/security_best_practices.mdx"


@dlt.resource(name="mcp_security_docs", write_disposition="merge", primary_key="doc_id")
def fetch_mcp_security() -> Generator[dict, None, None]:
    """Clone the MCP repo and yield the security best-practices doc.

    Reads ``security_best_practices.mdx`` from the cloned repo rather than
    scraping the Mintlify site. Splits the doc on top-level markdown headings
    into section rows.

    Yields:
        dict: A row with ``doc_id``, ``section_title``, ``content``,
        ``source``, and ``fetched_at``.

    Notes:
        On any clone/read failure this logs a warning and yields nothing
        (continue-and-report). The temp clone dir is always cleaned up.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                ["git", "clone", "--depth", "1", REPO_URL, tmpdir],
                check=True,
                capture_output=True,
            )
            doc_path = Path(tmpdir) / SECURITY_DOC
            if not doc_path.exists():
                logger.warning("MCP security doc not found at %s", SECURITY_DOC)
                return
            text = doc_path.read_text(encoding="utf-8")

            # Split on markdown H2 headings; keep a leading section for preamble.
            title = "Security Best Practices"
            buffer: list[str] = []
            section_index = 0
            for line in text.splitlines():
                if line.startswith("## "):
                    yield from _emit(section_index, title, buffer)
                    section_index += 1
                    title = line[3:].strip()
                    buffer = []
                else:
                    buffer.append(line)
            yield from _emit(section_index, title, buffer)
    except Exception as e:  # noqa: BLE001 - continue-and-report
        logger.warning("Source mcp_security_docs failed, skipping: %s", e)
        return


def _emit(index: int, title: str, lines: list[str]) -> Generator[dict, None, None]:
    """Yield a section row if it has non-empty content.

    Args:
        index: Zero-based section position within the doc.
        title: Section heading text.
        lines: Raw content lines for the section.

    Yields:
        dict: A merge-keyed section row, or nothing when the section is empty.
    """
    content = "\n".join(lines).strip()
    if not content:
        return
    yield {
        "doc_id": f"mcp_security::{index}",
        "section_title": title,
        "content": content,
        "source": "mcp_security_docs",
        "fetched_at": datetime.now(timezone.utc),
    }


@dlt.source
def mcp_security_source():
    """dlt source definition for the MCP security docs."""
    return [fetch_mcp_security()]
