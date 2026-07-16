"""LLM response generation with prompt variants"""

import os
from typing import AsyncGenerator, List, Dict, Any
from openai import AsyncOpenAI


class LLMGenerator:
    """Generate answers using OpenAI API"""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model

    async def stream_answer(
        self,
        query: str,
        context: str,
        prompt_variant: str = "base"
    ) -> AsyncGenerator[str, None]:
        """
        Stream answer using specified prompt variant.

        Variant A (base): Simple context + query
        Variant B (practitioner): Role-framed answer with structured output
        """
        if prompt_variant == "base":
            system_prompt = "You are a helpful security expert. Answer based only on provided context."
            user_prompt = f"Context:\n{context}\n\nQuestion: {query}"

        elif prompt_variant == "practitioner":
            system_prompt = "You are advising a security engineer on AI risks and LLM security."
            user_prompt = f"""Context:\n{context}

Question: {query}

Provide your answer in this structure:
1. Threat ID (if applicable, e.g., LLM01)
2. Risk Level (Critical/High/Medium/Low)
3. Key Mitigations (numbered list)
4. Control Mappings (OWASP/NIST alignments)

Use only provided context. Be concise."""

        else:
            raise ValueError(f"Unknown prompt variant: {prompt_variant}")

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5,
                max_tokens=500,
                stream=True
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            yield f"Error generating answer: {str(e)}"

    def generate_qa_pair(self, chunk_text: str, chunk_id: str) -> Dict[str, str]:
        """Generate a Q&A pair for evaluation (synchronous)"""
        # Placeholder: would call gpt-4o-mini to generate realistic Q&A
        return {
            "question": f"What does this chunk contain? (ID: {chunk_id})",
            "answer": f"This chunk is about security topics. (ID: {chunk_id})",
            "chunk_id": chunk_id
        }
