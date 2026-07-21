"""RED live-guarded contract: real INSERT + read-back lands in Postgres (MON-01).

Integration test, live-guarded by the ``pg_engine`` fixture — skips (never
errors) when Postgres is unreachable. Creates the tables idempotently, writes one
query row and one feedback row through ``QueryLogger(engine=pg_engine)``, then
reads both back with a Core ``select`` and asserts the written values are
present.

No hard foreign key is asserted from ``feedback_log`` to ``query_log`` (Pitfall
2): the query row is written after the stream completes, so feedback may precede
it; ``query_id`` is a plain indexed column.

RED until Wave 3 (05-03): ``monitoring.db`` and the engine-injected
``QueryLogger`` do not exist yet, so the imports/construction below raise (when
Postgres IS up). Offline, the fixture skips before any of that runs.
"""


def test_query_and_feedback_rows_persist(pg_engine):
    """A query row and a feedback row insert and read back with their written values (MON-01)."""
    from sqlalchemy import select

    from monitoring.db import feedback_log, metadata, query_log
    from monitoring.logging import QueryLogger

    metadata.create_all(pg_engine, checkfirst=True)

    import uuid

    qid = f"test-{uuid.uuid4().hex[:12]}"
    logger = QueryLogger(engine=pg_engine)
    logger.log_query(
        query_id=qid,
        user_id="u-live",
        query_text="what is prompt injection?",
        rewritten_query="LLM01 what is prompt injection?",
        detected_threat_id="LLM01",
        retrieval_mode="dense",
        prompt_variant="practitioner",
        total_latency_ms=1000,
    )
    logger.log_feedback(query_id=qid, rating=1)

    with pg_engine.connect() as conn:
        q = conn.execute(
            select(query_log).where(query_log.c.query_id == qid)
        ).mappings().all()
        f = conn.execute(
            select(feedback_log).where(feedback_log.c.query_id == qid)
        ).mappings().all()

    assert len(q) == 1
    assert q[0]["query_text"] == "what is prompt injection?"
    assert q[0]["retrieval_mode"] == "dense"
    assert len(f) == 1
    assert f[0]["rating"] == 1
