"""SQLAlchemy Core schema for query/feedback persistence (MON-01 / D-02).

Two append-only tables on a shared ``MetaData``, created idempotently at
startup via :func:`create_all`. Timestamps come from the DB
(``server_default=func.now()``) — no app-side ``datetime``. No hard foreign key
from ``feedback_log`` to ``query_log`` (Pitfall 2): the query row is written
after the stream completes, so a feedback insert may momentarily precede it;
``query_id`` is a plain indexed column.
"""

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
)

metadata = MetaData()

query_log = Table(
    "query_log",
    metadata,
    Column("query_id", String, primary_key=True),
    Column("user_id", String, nullable=True),
    Column("query_text", Text),
    Column("rewritten_query", Text),
    Column("detected_threat_id", String, nullable=True),
    Column("retrieval_mode", String),
    Column("prompt_variant", String),
    Column("top_score", Float),
    Column("refused", Integer),
    Column("retrieval_latency_ms", Integer),
    Column("total_latency_ms", Integer),
    Column("answer_length", Integer),
    Column("sources", Text),  # JSON string of cited threat_ids/sources
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

feedback_log = Table(
    "feedback_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("query_id", String, index=True),  # references query_log.query_id (no hard FK, Pitfall 2)
    Column("rating", Integer),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)


def create_all(engine) -> None:
    """Create the query/feedback tables if they don't already exist (idempotent).

    Args:
        engine: A SQLAlchemy sync ``Engine`` bound to the target database. This
            is table creation, not a migration framework — ``checkfirst=True``
            makes it a no-op when the tables already exist (D-02).
    """
    metadata.create_all(engine, checkfirst=True)
