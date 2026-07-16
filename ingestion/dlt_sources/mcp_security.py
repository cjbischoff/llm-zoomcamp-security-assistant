"""dlt source for MCP Security Documentation (Web Scrape)"""

import dlt
import requests
from bs4 import BeautifulSoup
from typing import Generator


@dlt.resource(name="mcp_security_docs", write_disposition="replace")
def fetch_mcp_security() -> Generator[dict, None, None]:
    """
    Scrape MCP security documentation from modelcontextprotocol.io.

    Focuses on threat modeling, best practices, and security considerations.
    """
    base_url = "https://modelcontextprotocol.io/specification/draft/basic/security_best_practices"

    try:
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Warning: Could not fetch MCP security docs: {e}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')

    # Extract sections
    section_counter = 0
    for section in soup.find_all(['h2', 'h3']):
        section_title = section.get_text().strip()
        if not section_title:
            continue

        section_content = ""
        for sibling in section.find_next_siblings():
            if sibling.name in ['h2', 'h3']:
                break
            if sibling.name in ['p', 'ul', 'ol', 'pre', 'code']:
                section_content += sibling.get_text() + "\n"

        if section_content.strip():
            section_counter += 1
            yield {
                "section_number": section_counter,
                "section_title": section_title,
                "content": section_content.strip(),
                "source": "mcp_security_docs",
                "url": base_url,
                "fetched_at": dlt.current.run_started_at,
            }


@dlt.source
def mcp_security_source():
    """dlt source definition for MCP Security Docs"""
    return [fetch_mcp_security()]
