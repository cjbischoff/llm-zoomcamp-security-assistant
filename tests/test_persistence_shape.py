"""RED contract for parameterized Core-insert row shaping (MON-01 / T-05-01).

Unit test, no live infra. ``QueryLogger`` is built with a MOCK engine; the
connection returned by ``engine.begin()`` records what statement is executed. The
contract: ``log_query`` / ``log_feedback`` execute a SQLAlchemy Core
``insert(...)`` targeting ``query_log`` / ``feedback_log`` with the expected
column values BOUND as parameters — never a raw SQL string (the SQL-injection
mitigation, T-05-01).

RED until Wave 3 (05-03): today ``QueryLogger.__init__`` takes no ``engine``, and
``monitoring.db`` (the table definitions) does not exist — so construction and
the table imports below raise. The plan that turns this green injects the engine
and runs ``conn.execute(insert(query_log).values(**row))``.
"""


def _conn_of(engine):
    """Return the connection object yielded by ``with engine.begin() as conn``."""
    return engine.begin.return_value.__enter__.return_value


def test_log_query_executes_parameterized_insert(mocker):
    """log_query runs insert(query_log).values(...) with bound params, no raw SQL (MON-01/T-05-01)."""
    from sqlalchemy.sql.dml import Insert

    from monitoring.db import query_log
    from monitoring.logging import QueryLogger

    engine = mocker.MagicMock()
    logger = QueryLogger(engine=engine)

    row = {
        "query_id": "qid-1",
        "user_id": "u-1",
        "query_text": "what is prompt injection?",
        "rewritten_query": "LLM01 what is prompt injection?",
        "detected_threat_id": "LLM01",
        "retrieval_mode": "dense",
        "prompt_variant": "practitioner",
        "total_latency_ms": 1234,
    }
    logger.log_query(**row)

    stmt = _conn_of(engine).execute.call_args.args[0]
    assert isinstance(stmt, Insert)  # Core insert, not a string
    assert not isinstance(stmt, str)
    assert stmt.table is query_log
    params = stmt.compile().params
    assert params["query_id"] == "qid-1"
    assert params["query_text"] == "what is prompt injection?"
    assert params["retrieval_mode"] == "dense"


def test_log_feedback_executes_parameterized_insert(mocker):
    """log_feedback runs insert(feedback_log).values(query_id, rating) with bound params (MON-01)."""
    from sqlalchemy.sql.dml import Insert

    from monitoring.db import feedback_log
    from monitoring.logging import QueryLogger

    engine = mocker.MagicMock()
    logger = QueryLogger(engine=engine)

    logger.log_feedback(query_id="qid-1", rating=1)

    stmt = _conn_of(engine).execute.call_args.args[0]
    assert isinstance(stmt, Insert)
    assert not isinstance(stmt, str)
    assert stmt.table is feedback_log
    params = stmt.compile().params
    assert params["query_id"] == "qid-1"
    assert params["rating"] == 1
