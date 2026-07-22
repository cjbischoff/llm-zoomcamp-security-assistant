"""RED contract for the deterministic content-hash point ID (ING-05).

Qdrant requires point IDs to be an unsigned int64 or a UUID string — never a
raw hex digest. ``point_id`` must be deterministic (same input → same id) and
sensitive to both position and text.

Imports of the target symbol are deferred into each test body so a
not-yet-implemented ``point_id`` produces a clean FAILURE (RED), never a
collection-time error. RED until Plan 01-04 lands.
"""

import uuid


def test_point_id_is_deterministic():
    """Same (source, position, text) yields an identical id across calls."""
    from ingestion.run_pipeline import point_id

    a = point_id("owasp_llm", 0, "prompt injection")
    b = point_id("owasp_llm", 0, "prompt injection")
    assert a == b


def test_point_id_varies_with_position():
    """A different position yields a different id."""
    from ingestion.run_pipeline import point_id

    assert point_id("owasp_llm", 0, "x") != point_id("owasp_llm", 1, "x")


def test_point_id_varies_with_text():
    """Different text yields a different id."""
    from ingestion.run_pipeline import point_id

    assert point_id("owasp_llm", 0, "x") != point_id("owasp_llm", 0, "y")


def test_point_id_is_a_valid_uuid_string():
    """The returned value parses as a UUID (Qdrant-legal id, not raw hex)."""
    from ingestion.run_pipeline import point_id

    value = point_id("owasp_llm", 0, "prompt injection")
    # Raises ValueError if not a UUID string → test fails, which is the point.
    parsed = uuid.UUID(str(value))
    assert str(parsed) == str(value)
