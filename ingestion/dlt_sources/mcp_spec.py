"""dlt source for MCP Protocol Specification"""

import dlt
import subprocess
import tempfile
from pathlib import Path
from typing import Generator


@dlt.resource(name="mcp_protocol_spec", write_disposition="replace")
def fetch_mcp_spec() -> Generator[dict, None, None]:
    """
    Clone MCP Protocol specification GitHub repo.

    One chunk per conceptual section (e.g., "Client-Server Model", "Protocol").
    """
    repo_url = "https://github.com/modelcontextprotocol/spec"

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(
            ["git", "clone", repo_url, tmpdir],
            check=True,
            capture_output=True
        )
        print(f"Cloned {repo_url}")

        repo_path = Path(tmpdir)
        for md_file in sorted(repo_path.glob("**/*.md")):
            # Focus on spec files
            if "README" in md_file.name and md_file.name != "README.md":
                continue

            content = md_file.read_text(encoding='utf-8')

            yield {
                "filename": md_file.name,
                "content": content,
                "source": "mcp_protocol_spec",
                "section": md_file.parent.name,
                "fetched_at": dlt.current.run_started_at,
            }


@dlt.source
def mcp_spec_source():
    """dlt source definition for MCP Protocol Spec"""
    return [fetch_mcp_spec()]
