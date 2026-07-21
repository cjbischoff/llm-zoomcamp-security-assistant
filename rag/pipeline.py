"""Full RAG pipeline orchestration"""

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator, Optional
from rag.rewriter import QueryRewriter
from rag.retrieval import DenseRetriever, HybridRetriever
from rag.generator import LLMGenerator
from ingestion.transforms.embed import Embedder
from monitoring.logging import QueryLogger
from monitoring.metrics import queries_total, query_latency, retrieval_scores

logger = logging.getLogger(__name__)

# retrieval_mode enum — validated at the trust boundary; never dispatch on the
# raw string (Security V5). dense is the default fast interactive path (D-06).
_RETRIEVAL_MODES = {"dense", "hybrid", "hybrid_rerank"}

# Deterministic grounding floor (D-02): if the top hit's cosine score is below
# this, the corpus does not cover the question — refuse without calling the LLM.
SCORE_FLOOR = 0.4
# Fixed, user-safe messages (D-03/T-02-12): never leak raw exception/connection detail.
_MSG_BACKEND_DOWN = "Retrieval backend is unavailable — please try again."
_MSG_COLLECTION_MISSING = "The knowledge base collection is not available."
_MSG_REFUSE = (
    "This isn't covered in the indexed sources "
    "(OWASP LLM/Agentic, MCP, NIST AI RMF)."
)


class RAGPipeline:
    """End-to-end RAG pipeline with monitoring"""

    def __init__(self, qdrant_client=None, aopenai=None, openai=None, engine=None):
        """Compose the pipeline, optionally injecting shared clients (INT-01/D-01).

        Every param defaults to None → today's per-instance self-construction, so
        the entire Phase 2/3/4 suite (which does ``RAGPipeline()`` then swaps
        attributes) stays green. When injected, no collaborator constructs a new
        client on the request path (SC1).

        Args:
            qdrant_client: Shared sync ``QdrantClient`` for the retrievers
                (kept sync, wrapped in ``asyncio.to_thread`` on the request path
                per D-01a — no switch to ``AsyncQdrantClient``).
            aopenai: Shared ``AsyncOpenAI`` for the generator.
            openai: Shared sync ``OpenAI`` for the embedder.
            engine: Shared SQLAlchemy engine for the query/feedback logger.
        """
        self.rewriter = QueryRewriter()
        self.embedder = Embedder(client=openai)
        self.retriever = DenseRetriever(client=qdrant_client)
        self.hybrid = HybridRetriever(client=qdrant_client)
        self.generator = LLMGenerator(client=aopenai)
        self.logger = QueryLogger(engine=engine)

    async def stream_answer(
        self,
        query: str,
        user_id: Optional[str] = None,
        prompt_variant: str = "practitioner",
        top_k: int = 5,
        # D-08: hybrid_rerank is the eval winner (hit_rate 84.62%, MRR 0.773) —
        # kept in sync with api.main QueryRequest.retrieval_mode (Pitfall 5).
        retrieval_mode: str = "hybrid_rerank",
        query_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Main pipeline: rewrite → embed → retrieve → gate → generate → log

        Streams answer tokens as they arrive. Below the 0.4 cosine floor, or on a
        retrieval outage, refuses with a fixed message and never calls the LLM.

        Args:
            query: The raw user question.
            user_id: Optional caller id for logging.
            prompt_variant: ``"practitioner"`` (default) or ``"base"``.
            top_k: Number of passages to retrieve.
            retrieval_mode: One of ``"dense"`` (fast interactive path — D-06),
                ``"hybrid"`` (dense+BM25+RRF), or ``"hybrid_rerank"`` (default,
                adds the cross-encoder; eval winner — D-08). Unknown values
                normalize to ``"dense"``
                (Security V5 — explicit membership, never dynamic dispatch). In
                the hybrid modes the blocking BM25/RRF/torch work runs off the
                event loop via :func:`asyncio.to_thread` (BON-01).
            query_id: Optional caller-supplied id (D-02a). When omitted a uuid4
                is generated; it is threaded to the persisted query_log row so
                feedback can reference the same query.
        """
        pipeline_start = time.time()

        # Validate the mode at entry; normalize anything unknown to dense (Security V5).
        if retrieval_mode not in _RETRIEVAL_MODES:
            retrieval_mode = "dense"

        # query_id is generated here if the caller didn't supply one, and threaded
        # through to the persisted query_log row (D-02a) so feedback can tie to it.
        query_id = query_id or str(uuid.uuid4())

        # Count every served query, refusals included (MON-02). Counter coherence
        # assumes a single uvicorn worker (Pitfall 3); Grafana-from-Postgres is the
        # primary path and is unaffected by multi-worker counter fragmentation.
        queries_total.labels(retrieval_approach=retrieval_mode).inc()

        # Step 1: Rewrite query -> detected canonical threat id (or None).
        original_query, detected_id = self.rewriter.rewrite(query)

        # Step 2: Embed query. The detected id biases the embed text (and, in the
        # hybrid modes, feeds the soft-boost); dense keeps its Phase-2 behavior.
        embed_text = f"{detected_id} {query}" if detected_id else query
        retrieval_start = time.time()
        # Embedding runs inside the streaming body (after the endpoint's
        # try/except has exited), so an OpenAI outage must be caught here and
        # degrade to the same fixed, non-leaking message as a retrieval outage
        # (WR-01 / D-03). A raw raise would abort the stream mid-response.
        try:
            # Synchronous OpenAI HTTP call — offload so it never blocks the
            # event loop (BON-01), matching the hybrid/rerank leg below.
            qvec = (await asyncio.to_thread(self.embedder.embed, [embed_text]))[0]
        except Exception:
            logger.error("Embedding backend failed", exc_info=True)
            yield _MSG_BACKEND_DOWN
            return

        # Step 2b: Route by mode. Hybrid/rerank run off the event loop (BON-01).
        if retrieval_mode == "dense":
            # Synchronous Qdrant query — offload off the event loop (BON-01);
            # dense is the default fast path, so this is the common case.
            result = await asyncio.to_thread(self.retriever.retrieve, qvec, top_k)
            gate_score = result["hits"][0]["score"] if result["hits"] else 0.0
        else:
            result = await asyncio.to_thread(
                self.hybrid.retrieve,
                qvec,
                query,
                detected_id,
                top_k,
                retrieval_mode == "hybrid_rerank",
            )
            gate_score = result.get("gate_score", 0.0)
        retrieval_latency_ms = (time.time() - retrieval_start) * 1000

        # Step 3: RET-02 status + 0.4 gate (deterministic, pre-generation — D-02/D-03).
        # The gate reads the dense COSINE reference only — never a fusion or
        # cross-encoder score (Pitfall 3).
        status = result["status"]
        hits = result["hits"]
        if status in ("backend_down", "backend_error"):
            yield _MSG_BACKEND_DOWN
            return
        if status == "collection_missing":
            yield _MSG_COLLECTION_MISSING
            return
        if not hits or gate_score < SCORE_FLOOR:
            yield _MSG_REFUSE
            # Persist the refusal (refused=1) — off-loop, never blocks (Pattern 4).
            total_latency_ms = (time.time() - pipeline_start) * 1000
            await asyncio.to_thread(
                self.logger.log_query,
                query_id=query_id,
                user_id=user_id,
                query_text=original_query,
                rewritten_query=embed_text,
                detected_threat_id=detected_id,
                retrieval_mode=retrieval_mode,
                prompt_variant=prompt_variant,
                top_score=gate_score,
                refused=1,
                retrieval_latency_ms=int(retrieval_latency_ms),
                total_latency_ms=int(total_latency_ms),
                answer_length=len(_MSG_REFUSE),
                sources="[]",
            )
            return

        # Step 4: Build citation-ready numbered context ([threat_id] + source — D-04)
        context = "\n\n".join(
            f"[{h['metadata'].get('threat_id', '?')}] "
            f"(source: {h['metadata'].get('source', '?')})\n{h['text']}"
            for h in hits
        )

        # Step 5: Generate answer (streaming) — the LLM sees the original question.
        # Accumulate tokens (still yielding each unchanged) so answer_length is
        # known at the end for the persisted row.
        answer_parts = []
        async for token in self.generator.stream_answer(
            query=query,
            context=context,
            prompt_variant=prompt_variant
        ):
            answer_parts.append(token)
            yield token

        # Step 6: Persist the answered query (refused=0) + observe latency/score.
        total_latency_ms = (time.time() - pipeline_start) * 1000
        query_latency.labels(retrieval_approach=retrieval_mode).observe(total_latency_ms / 1000)
        retrieval_scores.observe(gate_score)

        cited = [
            h["metadata"].get("threat_id")
            for h in hits
            if h.get("metadata", {}).get("threat_id")
        ]
        await asyncio.to_thread(
            self.logger.log_query,
            query_id=query_id,
            user_id=user_id,
            query_text=original_query,
            rewritten_query=embed_text,
            detected_threat_id=detected_id,
            retrieval_mode=retrieval_mode,
            prompt_variant=prompt_variant,
            top_score=gate_score,
            refused=0,
            retrieval_latency_ms=int(retrieval_latency_ms),
            total_latency_ms=int(total_latency_ms),
            answer_length=len("".join(answer_parts)),
            sources=json.dumps(cited),
        )
