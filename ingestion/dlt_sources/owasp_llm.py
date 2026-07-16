"""dlt source for OWASP LLM Top 10"""

import dlt
import subprocess
import tempfile
from pathlib import Path
from typing import Generator


@dlt.resource(name="owasp_llm_top_10", write_disposition="replace")
def fetch_owasp_llm() -> Generator[dict, None, None]:
    """
    Clone OWASP LLM Top 10 GitHub repo and extract markdown files.

    One chunk per threat (LLM01-LLM10).
    """
    repo_url = "https://github.com/OWASP/Top-10-for-LLM"

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(
            ["git", "clone", repo_url, tmpdir],
            check=True,
            capture_output=True
        )
        print(f"Cloned {repo_url}")

        repo_path = Path(tmpdir)
        for md_file in sorted(repo_path.glob("**/*.md")):
            # Filter to threat files (LLM01, LLM02, etc.)
            if "LLM" not in md_file.name:
                continue

            content = md_file.read_text(encoding='utf-8')
            threat_id = md_file.stem.split('_')[0] if '_' in md_file.stem else "UNKNOWN"

            yield {
                "filename": md_file.name,
                "threat_id": threat_id,
                "threat_name": md_file.stem.replace('_', ' '),
                "content": content,
                "source": "owasp_llm_top_10",
                "fetched_at": dlt.current.run_started_at,
            }


@dlt.source
def owasp_llm_source():
    """dlt source definition for OWASP LLM Top 10"""
    return [fetch_owasp_llm()]
