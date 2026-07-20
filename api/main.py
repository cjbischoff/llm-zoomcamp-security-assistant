"""FastAPI application for security RAG system"""

import os
import logging
from typing import AsyncGenerator, Literal, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Security RAG API",
    description="AI-powered threat intelligence RAG system",
    version="1.0.0"
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
    # so the pipeline never dispatches on an untrusted raw string. dense is the
    # default fast path (D-06).
    retrieval_mode: Literal["dense", "hybrid", "hybrid_rerank"] = "dense"
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
async def query_endpoint(request: QueryRequest):
    """
    Query the security RAG system.

    Streams answer tokens as they arrive.
    """
    try:
        # Import pipeline (lazy import to avoid circular dependencies)
        from rag.pipeline import RAGPipeline

        pipeline = RAGPipeline()

        async def answer_generator() -> AsyncGenerator[str, None]:
            """Stream answer from pipeline"""
            async for token in pipeline.stream_answer(
                query=request.query,
                user_id=request.user_id,
                prompt_variant=request.prompt_variant,
                retrieval_mode=request.retrieval_mode
            ):
                yield token

        return StreamingResponse(answer_generator(), media_type="text/plain")

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
