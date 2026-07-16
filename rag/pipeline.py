"""Full RAG pipeline orchestration"""

import time
import asyncio
from typing import AsyncGenerator, Dict, Any, List
from rag.rewriter import QueryRewriter
from rag.retrieval import HybridRetriever
from rag.generator import LLMGenerator
from monitoring.logging import QueryLogger


class RAGPipeline:
    """End-to-end RAG pipeline with monitoring"""

    def __init__(self):
        self.rewriter = QueryRewriter()
        self.retriever = HybridRetriever()
        self.generator = LLMGenerator()
        self.logger = QueryLogger()

    async def stream_answer(
        self,
        query: str,
        user_id: str = None,
        prompt_variant: str = "base"
    ) -> AsyncGenerator[str, None]:
        """
        Main pipeline: rewrite → retrieve → generate → log

        Streams answer tokens as they arrive.
        """
        pipeline_start = time.time()

        # Step 1: Rewrite query
        original_query, rewritten_query = self.rewriter.rewrite(query)

        # Step 2: Retrieve context (placeholder)
        # In production, would embed query and call retriever
        retrieval_start = time.time()
        retrieval_results = []  # Would be populated from actual retriever
        retrieval_latency_ms = (time.time() - retrieval_start) * 1000

        # Build context from retrieval results
        context = "\n---\n".join([r.get("text", "") for r in retrieval_results]) if retrieval_results else "No relevant documents found."

        # Step 3: Generate answer (streaming)
        async for token in self.generator.stream_answer(
            query=rewritten_query,
            context=context,
            prompt_variant=prompt_variant
        ):
            yield token

        # Step 4: Log query
        total_latency_ms = (time.time() - pipeline_start) * 1000

        self.logger.log_query(
            user_id=user_id,
            query_text=original_query,
            rewritten_query=rewritten_query,
            retrieval_latency_ms=int(retrieval_latency_ms),
            retrieval_approach="hybrid",
            top_5_scores=[r.get("score", 0) for r in retrieval_results[:5]],
            total_latency_ms=int(total_latency_ms),
            prompt_variant=prompt_variant
        )
