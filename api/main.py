"""FastAPI application for security RAG system"""

import asyncio
import os
import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Literal, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Shared-client constructors imported at module top so the lifespan builds them
# once and tests can patch api.main.<Name> (SC1/D-01). The sync QdrantClient is
# deliberate (D-01a): least churn to the working Phase-3 retrieval — it already
# runs off-loop via asyncio.to_thread; the load-bearing requirement is
# built-once-not-per-request, which injection satisfies.
from qdrant_client import QdrantClient
from openai import AsyncOpenAI, OpenAI
from sqlalchemy import create_engine, text
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from monitoring.db import metadata
from monitoring.metrics import user_feedback
# Shared retrievers built once in lifespan (CR-01) so the BM25 index + reranker
# are reused across requests instead of rebuilt per request.
from rag.retrieval import DenseRetriever, HybridRetriever

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the shared clients exactly once at startup and park them on app.state.

    Constructs QdrantClient, AsyncOpenAI, OpenAI, and a SQLAlchemy engine a single
    time (SC1/D-01) rather than per request, creates the query/feedback tables
    idempotently (``create_all(checkfirst=True)`` — D-02), yields for the app's
    lifetime, then closes the Qdrant client and disposes the engine on shutdown.
    Single-worker assumption for in-process counter coherence (Pitfall 3).

    Also builds ONE shared ``DenseRetriever`` + ``HybridRetriever`` on
    ``app.state`` (CR-01) so the expensive BM25 index and cross-encoder reranker
    are constructed once and reused across requests, not rebuilt per request.
    The BM25 index is eagerly warmed at startup (best-effort) so the first query
    does not pay the corpus-scroll cost; a cold/unpopulated corpus fails warming
    harmlessly and the index builds lazily (lock-guarded) on first use.

    Args:
        app: The FastAPI application whose ``state`` receives the clients.

    Yields:
        None: Control returns to the running application while clients live.
    """
    app.state.qdrant = QdrantClient(
        host=os.getenv("QDRANT_HOST", "localhost"),
        port=int(os.getenv("QDRANT_PORT", 6333)),
        check_compatibility=False,
    )
    app.state.aopenai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    app.state.openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    # pool_pre_ping guards against stale pooled connections (T-05-14).
    app.state.engine = create_engine(os.environ["POSTGRES_URL"], pool_pre_ping=True)
    # Idempotent DDL — no-op when the tables already exist (D-02).
    metadata.create_all(app.state.engine, checkfirst=True)

    # Shared retrievers built once and reused across requests (CR-01). The
    # HybridRetriever owns the BM25 index + cross-encoder — previously rebuilt on
    # every request. Both legs receive the shared Qdrant client (no per-request
    # client construction — SC1).
    app.state.dense = DenseRetriever(client=app.state.qdrant)
    app.state.hybrid = HybridRetriever(client=app.state.qdrant)
    # Best-effort eager warm of the BM25 index so the first hybrid query does not
    # pay the full corpus scroll. Never fatal: an unpopulated/unreachable corpus
    # (or a mocked client in tests) just defers to the lock-guarded lazy build.
    try:
        app.state.hybrid.bm25._ensure_index()
    except Exception:
        logger.warning("BM25 warm at startup failed; will build lazily", exc_info=True)

    try:
        yield
    finally:
        app.state.qdrant.close()
        app.state.engine.dispose()


app = FastAPI(
    title="Security RAG API",
    description="AI-powered threat intelligence RAG system",
    version="1.0.0",
    lifespan=lifespan,
)


class QueryRequest(BaseModel):
    """Query request model"""
    # Bound untrusted query at the trust boundary (Security V5, T-02-11): oversized
    # bodies are rejected with a 422 before embedding/generation. Generous enough
    # for real security questions; full injection guardrails are HRD-02 (v2).
    query: str = Field(..., max_length=4000)
    # Enum-bound at the trust boundary (Security V5, T-03-04, CR-01): an
    # out-of-enum value is a 422 at request validation — same discipline as
    # retrieval_mode below — so the generator's ValueError branch is unreachable
    # from the network boundary. "practitioner" is the default (D-05).
    prompt_variant: Literal["practitioner", "base"] = "practitioner"
    # Enum-bound at the trust boundary (Security V5, T-03-04): an out-of-enum value
    # is a 422 at request validation — same discipline as the max_length cap —
    # so the pipeline never dispatches on an untrusted raw string. hybrid_rerank
    # is the eval winner and the default (D-08); kept in sync with
    # RAGPipeline.stream_answer's default (Pitfall 5).
    retrieval_mode: Literal["dense", "hybrid", "hybrid_rerank"] = "hybrid_rerank"
    user_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    services: dict


class FeedbackRequest(BaseModel):
    """Feedback request body tied to a prior query_id (INT-02).

    ``rating`` is bound to ``Literal[-1, 1]`` (thumbs down / up) so an
    out-of-range value is a 422 at the trust boundary before the handler runs
    (Security V5, T-05-05).
    """
    query_id: str
    rating: Literal[-1, 1]


@app.get("/health")
async def health_check(http: Request):
    """Health check endpoint.

    Probes the real dependencies rather than asserting health unconditionally
    (WR-04): a check that cannot fail is worse than none. Qdrant is probed by
    reusing the shared ``app.state.qdrant`` client (WR-01 — no per-probe client
    is constructed or leaked), offloaded via ``asyncio.to_thread``; Postgres is
    probed with a ``SELECT 1`` on the shared ``app.state.engine`` (also offloaded
    via ``asyncio.to_thread``); the OpenAI key is checked for presence (no billed
    call). The connection string, DB password, and API key are never logged
    (T-05-07).

    Qdrant and Postgres are both critical: a 503 is returned when either is
    unreachable so orchestration/monitoring can restart or alert.

    Args:
        http: The FastAPI ``Request``, used to reach the shared clients.
    """
    services = {}

    # Qdrant — critical retrieval dependency; reuse the shared lifespan client
    # (WR-01) rather than building and leaking a throwaway QdrantClient per
    # probe. Offloaded off the event loop for symmetry with the Postgres probe.
    def _probe_qdrant():
        http.app.state.qdrant.get_collections()

    try:
        await asyncio.to_thread(_probe_qdrant)
        services["qdrant"] = "connected"
    except Exception:
        logger.error("Health check: Qdrant probe failed", exc_info=True)
        services["qdrant"] = "unavailable"

    # Postgres — critical persistence dependency; SELECT 1 on the shared engine.
    def _probe_pg():
        with http.app.state.engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    try:
        await asyncio.to_thread(_probe_pg)
        services["postgres"] = "connected"
    except Exception:
        logger.error("Health check: Postgres probe failed", exc_info=True)
        services["postgres"] = "unavailable"

    # OpenAI — presence check only; a live call would bill every health probe.
    services["openai"] = "configured" if os.getenv("OPENAI_API_KEY") else "unconfigured"

    healthy = (
        services["qdrant"] == "connected"
        and services["postgres"] == "connected"
        and services["openai"] == "configured"
    )
    payload = {"status": "healthy" if healthy else "degraded", "services": services}
    return JSONResponse(status_code=200 if healthy else 503, content=payload)


@app.post("/query")
async def query_endpoint(request: QueryRequest, http: Request):
    """Query the security RAG system, streaming answer tokens as they arrive.

    Mints a per-request uuid ``query_id`` (D-02a), rides it on the ``X-Query-Id``
    response header, and threads the SAME id into the pipeline so the persisted
    query row and any later feedback row share one id. The per-request
    ``RAGPipeline`` receives the lifespan-built clients from ``app.state`` — no
    client is constructed on the request path (SC1).

    The try/except cannot wrap the streaming body once it starts: the pipeline
    already degrades retrieval/OpenAI outages to fixed, non-leaking messages
    inside the stream (D-03). Setup errors before streaming still return a
    generic 500 (WR-02 / T-02-12).

    Args:
        request: The validated ``QueryRequest`` body (query cap + enum modes).
        http: The FastAPI ``Request``, used to reach ``app.state`` clients.

    Returns:
        StreamingResponse: ``text/plain`` token stream with an ``X-Query-Id`` header.
    """
    try:
        # Import pipeline (lazy import to avoid circular dependencies)
        from rag.pipeline import RAGPipeline

        query_id = str(uuid.uuid4())
        pipeline = RAGPipeline(
            qdrant_client=http.app.state.qdrant,
            aopenai=http.app.state.aopenai,
            openai=http.app.state.openai,
            engine=http.app.state.engine,
            # Inject the lifespan-built shared retrievers (CR-01): the BM25 index
            # and cross-encoder reranker are reused, not rebuilt per request.
            dense=http.app.state.dense,
            hybrid=http.app.state.hybrid,
        )

        async def answer_generator() -> AsyncGenerator[str, None]:
            """Stream answer from pipeline"""
            async for token in pipeline.stream_answer(
                query=request.query,
                user_id=request.user_id,
                prompt_variant=request.prompt_variant,
                retrieval_mode=request.retrieval_mode,
                query_id=query_id,
            ):
                yield token

        return StreamingResponse(
            answer_generator(),
            media_type="text/plain",
            headers={"X-Query-Id": query_id},
        )

    except Exception:
        # Log detail server-side; return a generic message so raw exception
        # text (host:port, module paths, config) never reaches the client
        # (WR-02 / D-03 / T-02-12).
        logger.error("Query error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@app.post("/feedback")
async def feedback_endpoint(body: FeedbackRequest, http: Request):
    """Persist a thumbs rating for a prior query and increment the counter (INT-02).

    The ``rating`` is validated as ``Literal[-1, 1]`` on ``FeedbackRequest`` (a
    malformed/out-of-range body is a 422 before this runs — Security V5). The
    insert runs off the event loop via ``asyncio.to_thread`` using the shared
    ``app.state.engine`` (T-05-14). Unexpected errors return a generic 500 with
    detail logged server-side (T-05-06); secrets are never logged (T-05-07).

    Args:
        body: The validated ``{query_id, rating}`` feedback body.
        http: The FastAPI ``Request``, used to reach the shared engine.

    Returns:
        dict: ``{"status": "logged"}`` on success.
    """
    try:
        from monitoring.logging import QueryLogger

        logger_instance = QueryLogger(engine=http.app.state.engine)
        await asyncio.to_thread(logger_instance.log_feedback, body.query_id, body.rating)
        user_feedback.labels(
            feedback_type="positive" if body.rating > 0 else "negative"
        ).inc()

        return {"status": "logged"}

    except Exception:
        logger.error("Feedback error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@app.get("/metrics")
async def metrics_endpoint():
    """Serve the live Prometheus registry in exposition format (INT-03/D-04a).

    Returns the real registered counters (rag_queries_total, rag_user_feedback,
    latency/score histograms) — not hardcoded zeros. The counters are registered
    at import in ``monitoring.metrics``.

    Returns:
        Response: ``generate_latest()`` bytes with ``CONTENT_TYPE_LATEST``.
    """
    # Set content-type via header, not media_type: Starlette appends a second
    # "charset=utf-8" to a text/* media_type, corrupting CONTENT_TYPE_LATEST.
    return Response(generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8000)),
        reload=True
    )
