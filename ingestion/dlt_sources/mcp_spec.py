"""dlt source for the MCP protocol specification (git-clone → mdx)."""

import logging
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import dlt

logger = logging.getLogger(__name__)

REPO_URL = "https://github.com/modelcontextprotocol/modelcontextprotocol"
# Latest spec version dir only — the spec files are .mdx, not .md.
SPEC_GLOB = "docs/specification/2025-11-25/**/*.mdx"


@dlt.resource(name="mcp_protocol_spec", write_disposition="merge", primary_key="doc_id")
def fetch_mcp_spec() -> Generator[dict, None, None]:
    """Clone the MCP repo and yield one row per spec ``.mdx`` file.

    Shallow-clones the ``modelcontextprotocol/modelcontextprotocol`` repo and
    globs the latest spec version dir (``2025-11-25``) for ``.mdx`` files.

    Yields:
        dict: A row with ``doc_id``, ``content``, ``source``, ``section``
        (parent dir), ``filename``, and ``fetched_at``.

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
            repo_path = Path(tmpdir)
            for mdx_file in sorted(repo_path.glob(SPEC_GLOB)):
                rel_path = mdx_file.relative_to(repo_path)
                content = mdx_file.read_text(encoding="utf-8")
                yield {
                    "doc_id": f"mcp_spec::{rel_path}",
                    "filename": mdx_file.name,
                    "content": content,
                    "source": "mcp_protocol_spec",
                    "section": mdx_file.parent.name,
                    "fetched_at": datetime.now(timezone.utc),
                }
    except Exception as e:  # noqa: BLE001 - continue-and-report
        logger.warning("Source mcp_protocol_spec failed, skipping: %s", e)
        return


@dlt.source
def mcp_spec_source():
    """dlt source definition for the MCP protocol spec."""
    return [fetch_mcp_spec()]
