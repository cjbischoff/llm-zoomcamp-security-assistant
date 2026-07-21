"""Seed the RAG stack with representative traffic so Grafana panels show data (SC5).

Fires a mix of in-corpus threat questions and a few off-corpus questions (which
trip the grounding-gate refusal) at ``POST /query``, across varied
``prompt_variant`` and ``retrieval_mode``, capturing each ``X-Query-Id`` from the
streaming response header. Then POSTs a spread of thumbs (mostly +1, some -1) to
``POST /feedback`` referencing those ids. The result is non-zero rows across all
six Postgres dashboard panels (query volume, latency, mode split, feedback ratio,
refusal rate, prompt-variant split).

Run against a live stack::

    python scripts/seed_queries.py --api-url http://localhost:8000

Exits non-zero if the API is unreachable so the operator sees the failure.
Handles no secrets and prints none.
"""

import argparse
import itertools
import sys

import httpx

# In-corpus questions — hit the real security corpus, should retrieve + answer.
IN_CORPUS = [
    "What is prompt injection and how do I mitigate it?",
    "How does training-data poisoning threaten an LLM?",
    "What are the security risks of the Model Context Protocol?",
    "How does the NIST AI RMF frame risk management for AI systems?",
    "What is excessive agency in agentic systems?",
    "How can I prevent sensitive information disclosure from an LLM?",
    "What is insecure output handling in LLM applications?",
    "How do supply-chain vulnerabilities affect LLM deployments?",
    "What controls reduce the risk of model denial of service?",
    "How should I secure a retrieval-augmented generation pipeline?",
]

# Off-corpus questions — no grounding, should trip the refusal gate (SC5 refusal panel).
OFF_CORPUS = [
    "What is the best recipe for sourdough bread?",
    "Who won the 2018 FIFA World Cup?",
    "How do I change a car tire?",
]

PROMPT_VARIANTS = ["practitioner", "base"]
RETRIEVAL_MODES = ["dense", "hybrid", "hybrid_rerank"]


def _fire_query(client: httpx.Client, api_url: str, query: str,
                prompt_variant: str, retrieval_mode: str) -> str | None:
    """POST one /query, drain the stream, and return the X-Query-Id header.

    Args:
        client: A reusable sync ``httpx.Client``.
        api_url: Base API URL (no trailing slash), e.g. ``http://localhost:8000``.
        query: The question text.
        prompt_variant: One of ``practitioner`` / ``base``.
        retrieval_mode: One of ``dense`` / ``hybrid`` / ``hybrid_rerank``.

    Returns:
        The ``X-Query-Id`` string if the stream opened, else ``None``.
    """
    payload = {
        "query": query,
        "prompt_variant": prompt_variant,
        "retrieval_mode": retrieval_mode,
    }
    with client.stream("POST", f"{api_url}/query", json=payload) as resp:
        resp.raise_for_status()
        query_id = resp.headers.get("X-Query-Id")
        # Drain the body so the pipeline completes and writes the query row.
        for _ in resp.iter_bytes():
            pass
    return query_id


def main() -> int:
    """Drive a representative query+feedback batch against the API.

    Returns:
        Process exit code: 0 on success, non-zero if the API is unreachable.
    """
    parser = argparse.ArgumentParser(description="Seed the RAG stack for Grafana (SC5).")
    parser.add_argument("--api-url", default="http://localhost:8000",
                        help="Base API URL (default: http://localhost:8000)")
    parser.add_argument("--count", type=int, default=18,
                        help="Approximate number of queries to fire (default: 18)")
    args = parser.parse_args()
    api_url = args.api_url.rstrip("/")

    # Build a varied batch: cycle in-corpus questions across variant/mode, then
    # append the off-corpus refusals so the refusal-rate panel is non-zero.
    combos = itertools.cycle(
        (pv, rm) for pv in PROMPT_VARIANTS for rm in RETRIEVAL_MODES
    )
    in_corpus_n = max(args.count - len(OFF_CORPUS), 1)
    batch = []
    for i in range(in_corpus_n):
        pv, rm = next(combos)
        batch.append((IN_CORPUS[i % len(IN_CORPUS)], pv, rm))
    for q in OFF_CORPUS:
        pv, rm = next(combos)
        batch.append((q, pv, rm))

    query_ids: list[str] = []
    with httpx.Client(timeout=120.0) as client:
        for query, pv, rm in batch:
            try:
                qid = _fire_query(client, api_url, query, pv, rm)
            except httpx.HTTPError as exc:
                print(f"ERROR: cannot reach {api_url}/query ({exc.__class__.__name__}).",
                      file=sys.stderr)
                return 1
            if qid:
                query_ids.append(qid)

        # Spread of thumbs: ~75% positive. Reference the captured query ids so
        # feedback_log rows join back to query_log.
        pos = neg = 0
        for idx, qid in enumerate(query_ids):
            rating = -1 if idx % 4 == 0 else 1
            try:
                client.post(f"{api_url}/feedback",
                            json={"query_id": qid, "rating": rating}).raise_for_status()
            except httpx.HTTPError as exc:
                print(f"ERROR: cannot reach {api_url}/feedback ({exc.__class__.__name__}).",
                      file=sys.stderr)
                return 1
            if rating > 0:
                pos += 1
            else:
                neg += 1

    print(f"Seeded {len(batch)} queries "
          f"({in_corpus_n} in-corpus, {len(OFF_CORPUS)} off-corpus/refusal); "
          f"posted {pos + neg} feedback rows ({pos} up, {neg} down).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
