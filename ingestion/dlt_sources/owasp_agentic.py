"""dlt source for OWASP Agentic Top 10"""

import dlt
import subprocess
import tempfile
from pathlib import Path
from typing import Generator


@dlt.resource(name="owasp_agentic_top_10", write_disposition="replace")
def fetch_owasp_agentic() -> Generator[dict, None, None]:
    """
    Clone OWASP Agentic Top 10 GitHub repo and extract markdown files.

    One chunk per threat, tagged as [AGENTIC] to distinguish from LLM-only threats.
    """
    repo_url = "https://github.com/OWASP/www-project-agentic-top-10"

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(
            ["git", "clone", repo_url, tmpdir],
            check=True,
            capture_output=True
        )
        print(f"Cloned {repo_url}")

        repo_path = Path(tmpdir)
        for md_file in sorted(repo_path.glob("**/*.md")):
            if "agentic" not in md_file.name.lower() and "threat" not in md_file.name.lower():
                continue

            content = md_file.read_text(encoding='utf-8')
            threat_id = f"AGENTIC-{md_file.stem.split('_')[0]}" if '_' in md_file.stem else "AGENTIC-XX"

            yield {
                "filename": md_file.name,
                "threat_id": threat_id,
                "threat_name": f"[AGENTIC] {md_file.stem.replace('_', ' ')}",
                "content": content,
                "source": "owasp_agentic_top_10",
                "fetched_at": dlt.current.run_started_at,
            }


@dlt.source
def owasp_agentic_source():
    """dlt source definition for OWASP Agentic Top 10"""
    return [fetch_owasp_agentic()]
