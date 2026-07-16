"""dlt source for the OWASP LLM Top 10 (git-clone → markdown)."""

import logging
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import dlt

logger = logging.getLogger(__name__)

REPO_URL = (
    "https://github.com/OWASP/"
    "www-project-top-10-for-large-language-model-applications"
)


@dlt.resource(name="owasp_llm_top_10", write_disposition="merge", primary_key="doc_id")
def fetch_owasp_llm() -> Generator[dict, None, None]:
    """Clone the OWASP LLM Top 10 repo and yield one row per threat file.

    Shallow-clones the repo, globs the ``2_0_vulns/LLM01..LLM10`` threat
    markdown files (excluding the preface and release candidates), and yields
    a flat, merge-keyed row per threat.

    Yields:
        dict: A row with ``doc_id``, ``threat_id`` (e.g. ``LLM01``),
        ``threat_name``, ``content``, ``source``, and ``fetched_at``.

    Notes:
        On any clone/read failure this logs a warning and yields nothing so the
        orchestrator's continue-and-report policy can drop the source without
        aborting the run. The temp clone dir is always cleaned up.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            subprocess.run(
                ["git", "clone", "--depth", "1", REPO_URL, tmpdir],
                check=True,
                capture_output=True,
            )
            repo_path = Path(tmpdir)
            threat_files = sorted(repo_path.glob("2_0_vulns/LLM0[1-9]*.md")) + sorted(
                repo_path.glob("2_0_vulns/LLM10*.md")
            )
            for md_file in threat_files:
                if md_file.name == "LLM00_Preface.md":
                    continue
                content = md_file.read_text(encoding="utf-8")
                threat_id = md_file.stem.split("_")[0]  # e.g. LLM01
                yield {
                    "doc_id": f"owasp_llm::{md_file.name}",
                    "threat_id": threat_id,
                    "threat_name": md_file.stem.replace("_", " "),
                    "content": content,
                    "source": "owasp_llm_top_10",
                    "fetched_at": datetime.now(timezone.utc),
                }
    except Exception as e:  # noqa: BLE001 - continue-and-report
        logger.warning("Source owasp_llm_top_10 failed, skipping: %s", e)
        return


@dlt.source
def owasp_llm_source():
    """dlt source definition for the OWASP LLM Top 10."""
    return [fetch_owasp_llm()]
