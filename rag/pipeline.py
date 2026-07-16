"""Full RAG pipeline orchestration"""

import time
from typing import AsyncGenerator, Optional
from rag.rewriter import QueryRewriter
from rag.retrieval import DenseRetriever
from rag.generator import LLMGenerator
from ingestion.transforms.embed import Embedder
from monitoring.logging import QueryLogger

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

    def __init__(self):
        self.rewriter = QueryRewriter()
        self.embedder = Embedder()
        self.retriever = DenseRetriever()
        self.generator = LLMGenerator()
        self.logger = QueryLogger()

    async def stream_answer(
        self,
        query: str,
        user_id: Optional[str] = None,
        prompt_variant: str = "practitioner",
        top_k: int = 5,
    ) -> AsyncGenerator[str, None]:
        """
        Main pipeline: rewrite → embed → retrieve → gate → generate → log

        Streams answer tokens as they arrive. Below the 0.4 cosine floor, or on a
        retrieval outage, refuses with a fixed message and never calls the LLM.
        """
        pipeline_start = time.time()

        # Step 1: Rewrite query (pass-through this phase; ASI remap is Phase 3)
        original_query, rewritten_query = self.rewriter.rewrite(query)

        # Step 2: Embed query (reuse Phase 1 Embedder, native 1536) and retrieve
        retrieval_start = time.time()
        qvec = self.embedder.embed([rewritten_query])[0]
        result = self.retriever.retrieve(qvec, top_k=top_k)
        retrieval_latency_ms = (time.time() - retrieval_start) * 1000

        # Step 3: RET-02 status + 0.4 gate (deterministic, pre-generation — D-02/D-03)
        status = result["status"]
        hits = result["hits"]
        if status in ("backend_down", "backend_error"):
            yield _MSG_BACKEND_DOWN
            return
        if status == "collection_missing":
            yield _MSG_COLLECTION_MISSING
            return
        if not hits or hits[0]["score"] < SCORE_FLOOR:
            yield _MSG_REFUSE
            return

        # Step 4: Build citation-ready numbered context ([threat_id] + source — D-04)
        context = "\n\n".join(
            f"[{h['metadata'].get('threat_id', '?')}] "
            f"(source: {h['metadata'].get('source', '?')})\n{h['text']}"
            for h in hits
        )

        # Step 5: Generate answer (streaming)
        async for token in self.generator.stream_answer(
            query=rewritten_query,
            context=context,
            prompt_variant=prompt_variant
        ):
            yield token

        # Step 6: Log query (persistence is Phase 5)
        total_latency_ms = (time.time() - pipeline_start) * 1000

        self.logger.log_query(
            user_id=user_id,
            query_text=original_query,
            rewritten_query=rewritten_query,
            retrieval_latency_ms=int(retrieval_latency_ms),
            retrieval_approach="dense",
            top_5_scores=[h.get("score", 0) for h in hits[:5]],
            total_latency_ms=int(total_latency_ms),
            prompt_variant=prompt_variant
        )
