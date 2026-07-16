"""Generate ground truth Q&A pairs using LLM"""

import json
import csv
import os
from typing import List, Dict
from openai import OpenAI


class QAGenerator:
    """Generate Q&A pairs for evaluation"""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model

    def generate_qa_for_chunk(self, chunk_text: str, chunk_id: str, source: str) -> List[Dict]:
        """Generate 1-2 Q&A pairs for a chunk"""
        prompt = f"""Given this security documentation chunk, generate 1-2 realistic questions
a security engineer might ask to retrieve this information.

Chunk ID: {chunk_id}
Source: {source}
Text: {chunk_text[:1000]}

Output as JSON array:
[
  {{"question": "...", "answer": "...", "chunk_id": "{chunk_id}", "source": "{source}"}}
]

Generate practical questions (not trivial). Be concise."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300
            )

            content = response.choices[0].message.content
            # Parse JSON response
            start = content.find('[')
            end = content.rfind(']') + 1
            if start >= 0 and end > start:
                qa_data = json.loads(content[start:end])
                return qa_data if isinstance(qa_data, list) else [qa_data]
            return []
        except Exception as e:
            print(f"Error generating Q&A: {e}")
            return []

    def generate_all_qa(self, chunks_file: str, output_file: str = "evaluation/ground_truth.csv"):
        """Generate Q&A for all chunks in JSON file"""
        # Load chunks
        if not os.path.exists(chunks_file):
            print(f"Chunks file not found: {chunks_file}")
            return

        with open(chunks_file) as f:
            chunks = json.load(f)

        all_qa = []
        for i, chunk in enumerate(chunks):
            print(f"Generating Q&A for chunk {i+1}/{len(chunks)}...")
            qa_pairs = self.generate_qa_for_chunk(
                chunk.get("text", ""),
                chunk_id=i,
                source=chunk.get("metadata", {}).get("source", "unknown")
            )
            all_qa.extend(qa_pairs)

        # Save as CSV
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["question", "answer", "chunk_id", "source"])
            writer.writeheader()
            writer.writerows(all_qa)

        print(f"Generated {len(all_qa)} Q&A pairs → {output_file}")


if __name__ == "__main__":
    generator = QAGenerator()
    generator.generate_all_qa("data/chunks.json")
