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


@app.get("/health")
async def health_check():
    """Health check endpoint.

    Probes the real dependencies rather than asserting health unconditionally
    (WR-04): a check that cannot fail is worse than none. Qdrant is probed with
    a short-timeout ``get_collections()``; the OpenAI key is checked for
    presence (no billed API call). Postgres logging is still a Phase-5
    placeholder (``monitoring.logging`` does not open a connection yet), so it
    is reported ``"unverified"`` rather than falsely ``"connected"``.

    Returns a 503 when a critical dependency (Qdrant) is unreachable so
    orchestration/monitoring can restart or alert.
    """
    services = {}

    # Qdrant — the one live, critical dependency for retrieval.
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", 6333)),
            timeout=2,
            check_compatibility=False,
        )
        client.get_collections()
        services["qdrant"] = "connected"
    except Exception:
        logger.error("Health check: Qdrant probe failed", exc_info=True)
        services["qdrant"] = "unavailable"

    # OpenAI — presence check only; a live call would bill every health probe.
    services["openai"] = "configured" if os.getenv("OPENAI_API_KEY") else "unconfigured"

    # Postgres logging is a Phase-5 placeholder — no connection to probe yet.
    services["postgres"] = "unverified"

    healthy = services["qdrant"] == "connected" and services["openai"] == "configured"
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
async def feedback_endpoint(query_id: str, feedback: int):
    """
    Log user feedback (-1: not helpful, 0: neutral, 1: helpful)
    """
    try:
        from monitoring.logging import QueryLogger

        logger_instance = QueryLogger()
        logger_instance.log_feedback(query_id, feedback)

        return {"status": "logged"}

    except Exception:
        logger.error("Feedback error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@app.get("/metrics")
async def metrics_endpoint():
    """Get current system metrics"""
    try:
        from monitoring.metrics import MetricsCollector

        collector = MetricsCollector()
        return collector.get_metrics()

    except Exception:
        logger.error("Metrics error", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 8000)),
        reload=True
    )
