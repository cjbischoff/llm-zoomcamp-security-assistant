"""Evaluate LLM answer quality using LLM-as-judge"""

import json
import csv
import os
from typing import List, Dict
from openai import OpenAI


class LLMEvaluator:
    """Score LLM answers using another LLM as judge"""

    def __init__(self, judge_model: str = "gpt-4o"):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.judge_model = judge_model

    def judge_answer(self, query: str, answer: str, context: str) -> Dict:
        """Use LLM as judge to score answer (1-5 scale)"""
        prompt = f"""You are evaluating a security expert's answer.

Question: {query}
Answer: {answer[:500]}
Context: {context[:300]}

Score on 1-5 scale:
1. Accuracy: Does answer match source?
2. Completeness: Covers mitigations/controls?
3. No Hallucination: Threat IDs real and accurate?

Respond with JSON:
{{"accuracy": N, "completeness": N, "no_hallucination": N, "feedback": "..."}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.judge_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )

            content = response.choices[0].message.content
            start = content.find('{')
            end = content.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
            return {"accuracy": 0, "completeness": 0, "no_hallucination": 0}
        except Exception as e:
            print(f"Judge error: {e}")
            return {"accuracy": 0, "completeness": 0, "no_hallucination": 0}

    def evaluate_variants(self, queries_file: str, output_file: str = "evaluation/results/llm_eval.csv"):
        """Compare Base vs Practitioner prompt variants"""
        # Placeholder: load test queries and evaluate both variants
        results = []

        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["query", "variant", "accuracy", "completeness", "no_hallucination"])
            writer.writeheader()
            writer.writerows(results)

        print(f"LLM evaluation → {output_file}")


if __name__ == "__main__":
    evaluator = LLMEvaluator()
    evaluator.evaluate_variants("evaluation/test_queries.txt")
