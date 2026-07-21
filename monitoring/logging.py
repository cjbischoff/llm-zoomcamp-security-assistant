"""Query logging and instrumentation"""

import logging

from sqlalchemy import insert

from monitoring.db import feedback_log, query_log

logger = logging.getLogger(__name__)


class QueryLogger:
    """Persist queries/feedback to Postgres via parameterized Core inserts.

    The engine is injected (INT-01). These methods are SYNCHRONOUS — the async
    pipeline offloads them via :func:`asyncio.to_thread` (Pattern 4). Only
    ``query_id`` is ever logged; the connection string, DB password, and API key
    are never logged (T-05-02). All SQL is a bound ``insert().values()`` — no raw
    SQL string is ever constructed (T-05-01).
    """

    def __init__(self, engine=None):
        """Store the injected engine.

        Args:
            engine: A SQLAlchemy sync ``Engine``. When None, inserts are a safe
                offline no-op (keeps unit tests network-free; never crashes).
        """
        self.engine = engine

    def log_query(self, **row):
        """Insert one query row into ``query_log`` (parameterized, T-05-01).

        Args:
            **row: Column values for ``query_log`` — e.g. ``query_id``,
                ``user_id``, ``query_text``, ``rewritten_query``,
                ``detected_threat_id``, ``retrieval_mode``, ``prompt_variant``,
                ``top_score``, ``refused``, ``retrieval_latency_ms``,
                ``total_latency_ms``, ``answer_length``, ``sources``. Unspecified
                columns take their DB defaults. When the engine is None this is a
                no-op that logs only ``query_id``.
        """
        if self.engine is None:
            logger.info("Query logged (no engine): %s", row.get("query_id"))
            return
        with self.engine.begin() as conn:
            conn.execute(insert(query_log).values(**row))

    def log_feedback(self, query_id: str, rating: int):
        """Insert one feedback row into ``feedback_log`` (parameterized, T-05-01).

        Args:
            query_id: The query this feedback references (plain column, no FK).
            rating: Thumbs value (+1 / -1). When the engine is None this is a
                no-op that logs only ``query_id``.
        """
        if self.engine is None:
            logger.info("Feedback logged (no engine): %s", query_id)
            return
        with self.engine.begin() as conn:
            conn.execute(insert(feedback_log).values(query_id=query_id, rating=rating))


class MetricsCollector:
    """Collect system metrics for monitoring"""

    def get_metrics(self) -> dict:
        """Get current metrics"""
        return {
            "queries_total": 0,
            "queries_today": 0,
            "avg_latency_ms": 0,
            "feedback_rate": 0.0,
            "top_threats": []
        }
