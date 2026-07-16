"""dlt source for the OWASP Top 10 for Agentic Applications (git-clone → markdown).

The 2026 framework (ASI01–ASI10 taxonomy) is published as a *gated* PDF on
genai.owasp.org (a lead-capture wall — not machine-fetchable). The authoritative,
openly fetchable form of the ASI01–ASI10 content lives in the OWASP GenAI Data
Security Initiative's crosswalk repository (CC BY-SA 4.0), which maps every
Agentic Top 10 entry to established security frameworks with per-threat
descriptions, test categories, attack techniques, and weaknesses.

This source shallow-clones that repo and ingests a curated set of OWASP-native
and attack/testing-focused crosswalk files, yielding one row per ASI section so
downstream chunks carry the real ``ASI01``–``ASI10`` citation ids. Remapping the
rewriter's ``THREAT_MAPPINGS`` from the scaffold's ``AGENTIC-01`` scheme to the
``ASI`` ids is a Phase 3 dependency, out of scope here.
"""

import logging
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import dlt

logger = logging.getLogger(__name__)

# OWASP-official (GenAI Data Security Initiative). Public repo; shallow-cloned.
REPO_URL = "https://github.com/GenAI-Security-Project/GenAI-Data-Security-Initiative"
CROSSWALK_SUBDIR = "crosswalk/agentic-top10"

# Curated, high-signal crosswalk files: OWASP-native testing/verification
# (AITG, ASVS) plus attack techniques (MITRE ATLAS) and concrete weaknesses
# (CWE/CVE). Each carries all ten ASI entries with per-threat descriptions.
CURATED_FILES = (
    "Agentic_AITG.md",        # OWASP AI Testing Guide — how to test each threat
    "Agentic_MITREATLAS.md",  # MITRE ATLAS — real-world attack techniques
    "Agentic_CWE_CVE.md",     # concrete weaknesses / CVEs per threat
    "Agentic_ASVS.md",        # OWASP ASVS — verification requirements
)

# Section headings look like: "### ASI01 — Agent Goal Hijack" (em dash, en dash,
# or hyphen). Capture the two-digit id and the threat name.
_ASI_HEADING = re.compile(r"(?m)^#{2,4}\s+ASI(\d{2})\s*[—–-]\s*(.+?)\s*$")


def _split_sections(text: str) -> Generator[tuple, None, None]:
    """Yield ``(asi_id, threat_name, section_text)`` per ASI heading in a file.

    Args:
        text: Full markdown content of one crosswalk file.

    Yields:
        tuple: ``(asi_id, threat_name, section_text)`` where ``asi_id`` is e.g.
            ``ASI01`` and ``section_text`` spans from one ASI heading up to the
            next (or end of file).
    """
    matches = list(_ASI_HEADING.finditer(text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        asi_id = f"ASI{m.group(1)}"
        threat_name = m.group(2).strip()
        yield asi_id, threat_name, text[start:end].strip()


@dlt.resource(name="owasp_agentic_top_10", write_disposition="merge", primary_key="doc_id")
def fetch_owasp_agentic() -> Generator[dict, None, None]:
    """Clone the OWASP crosswalk repo and yield one row per ASI section.

    Shallow-clones the GenAI Data Security Initiative repo, reads the curated
    ``crosswalk/agentic-top10`` files, splits each on its ``ASI01``–``ASI10``
    headings, and yields a merge-keyed row per section tagged with the real ASI
    id and threat name.

    Yields:
        dict: A row with ``doc_id``, ``threat_id`` (e.g. ``ASI01``),
        ``threat_name``, ``content``, ``source``, ``url``, and ``fetched_at``.

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
            base = Path(tmpdir) / CROSSWALK_SUBDIR
            emitted = 0
            for filename in CURATED_FILES:
                md_file = base / filename
                if not md_file.exists():
                    logger.warning("  crosswalk file missing, skipping: %s", filename)
                    continue
                framework = md_file.stem.replace("Agentic_", "")
                content = md_file.read_text(encoding="utf-8")
                for asi_id, threat_name, section in _split_sections(content):
                    if len(section.split()) < 30:  # skip stubs
                        continue
                    yield {
                        "doc_id": f"owasp_agentic::{framework}::{asi_id}",
                        "threat_id": asi_id,
                        "threat_name": f"{asi_id} {threat_name}",
                        "content": section,
                        "source": "owasp_agentic_top_10",
                        "url": f"{REPO_URL}/blob/HEAD/{CROSSWALK_SUBDIR}/{filename}",
                        "fetched_at": datetime.now(timezone.utc),
                    }
                    emitted += 1
            if emitted == 0:
                logger.warning("Source owasp_agentic_top_10 yielded no sections (repo layout changed?)")
    except Exception as e:  # noqa: BLE001 - continue-and-report
        logger.warning("Source owasp_agentic_top_10 failed, skipping: %s", e)
        return


@dlt.source
def owasp_agentic_source():
    """dlt source definition for the OWASP Agentic Top 10."""
    return [fetch_owasp_agentic()]
