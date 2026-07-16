"""RED contract for per-source fetch resilience (ING-01, continue-and-report).

Network-gated: skips cleanly when there is no egress. For each of the 5 dlt
resources, materializing the resource must either yield >= 1 row OR yield
nothing gracefully — it must NEVER raise an unhandled exception that would
abort the whole run (the continue-and-report policy, D-07 discretion).

Heavy imports (dlt + the source modules) are deferred into the test body so
this file collects cleanly even when dlt is not installed. RED until Plan
01-03 repairs the dead source URLs / adds the resilient fetch path.
"""

import socket

import pytest

# (module path, resource-function name) for each of the 5 sources.
SOURCES = [
    ("ingestion.dlt_sources.owasp_llm", "fetch_owasp_llm"),
    ("ingestion.dlt_sources.owasp_agentic", "fetch_owasp_agentic"),
    ("ingestion.dlt_sources.mcp_spec", "fetch_mcp_spec"),
    ("ingestion.dlt_sources.mcp_security", "fetch_mcp_security"),
    ("ingestion.dlt_sources.nist_ai_rmf", "fetch_nist_ai_rmf"),
]


@pytest.fixture
def require_network():
    """Skip the test when the network is unreachable.

    Attempts a short TCP connect to github.com:443 (the sources clone from
    GitHub / download over HTTPS). Skips — never errors — when offline.
    """
    try:
        socket.setdefaulttimeout(3.0)
        socket.create_connection(("github.com", 443)).close()
    except OSError as exc:
        pytest.skip(f"network unreachable: {exc}")


@pytest.mark.parametrize("module_path, fn_name", SOURCES)
def test_source_fetch_never_raises_unhandled(require_network, module_path, fn_name):
    """Fetching a source yields rows or nothing, but never raises (ING-01)."""
    import importlib

    module = importlib.import_module(module_path)
    fetch = getattr(module, fn_name)

    try:
        rows = list(fetch())
    except Exception as exc:  # noqa: BLE001 - contract: must not propagate
        pytest.fail(
            f"{module_path}.{fn_name} raised instead of continue-and-report: {exc!r}"
        )

    assert isinstance(rows, list)
