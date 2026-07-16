# Testing Patterns

**Analysis Date:** 2026-07-16

## Test Framework

**Runner:**
- None configured. No `pytest.ini`, `tox.ini`, `pyproject.toml`, or `conftest.py` in the repo.
- No `tests/` directory and no `test_*.py` / `*_test.py` files exist.
- `requirements.txt` lists `httpx==0.25.2` and `scikit-learn==1.3.2` under a "Development" / "Evaluation & Testing" section, but no test runner (`pytest`) is declared.

**Assertion Library:**
- Not applicable — no tests written yet.

**Run Commands:**
```bash
# No test command exists yet. Recommended baseline once tests are added:
pip install pytest pytest-asyncio
pytest                      # Run all tests
pytest -k <pattern>         # Run subset
pytest --cov=rag --cov=api  # Coverage (requires pytest-cov)
```

## Test File Organization

**Location:**
- Not established. Recommend a top-level `tests/` mirroring package layout (`tests/rag/`, `tests/api/`, `tests/ingestion/`).

**Naming:**
- Not established. Adopt `test_<module>.py` with `test_<behavior>` functions.

## Test Structure

Not applicable — no test suites exist. When added, note that async code dominates
(`RAGPipeline.stream_answer`, `LLMGenerator.stream_answer`, FastAPI routes) and will
need `pytest-asyncio` with `@pytest.mark.asyncio`.

## Mocking

**Framework:** None in use. Recommend stdlib `unittest.mock` plus `httpx.MockTransport` / FastAPI `TestClient`.

**What to Mock (based on external boundaries in code):**
- OpenAI `AsyncOpenAI` client (`rag/generator.py`) — mock `chat.completions.create` stream
- Qdrant `QdrantClient` (`rag/retrieval.py`) — mock `.search()`
- PostgreSQL logging (`monitoring/logging.py`) — currently stubbed, mock once wired

**What NOT to Mock:**
- Pure logic: `QueryRewriter.rewrite` and `normalize_threat_id` (`rag/rewriter.py`), `Chunker` methods (`ingestion/transforms/chunk.py`), and `RetrieverEvaluator` metric math (`evaluation/eval_retrieval.py`) are deterministic and should be tested directly.

## Fixtures and Factories

**Test Data:**
- No fixtures directory. `evaluation/` reads ground-truth Q&A from CSV (`RetrieverEvaluator.load_ground_truth`) and writes JSON results to `evaluation/results/` — this is evaluation infrastructure, not unit-test fixtures.

**Location:**
- None established.

## Coverage

**Requirements:** None enforced. No coverage tooling configured.

**View Coverage:**
```bash
# Not configured. Add pytest-cov and:
pytest --cov=. --cov-report=term-missing
```

## Test Types

**Unit Tests:** None. Highest-value first targets (pure, no I/O):
- `rag/rewriter.py` — threat-ID mapping and normalization
- `ingestion/transforms/chunk.py` — chunk boundaries, char caps, short-section skip
- `evaluation/eval_retrieval.py` — Hit Rate / MRR / Precision math

**Integration Tests:** None. Candidates: FastAPI endpoints via `TestClient` (`/health`, `/query`, `/feedback`, `/metrics` in `api/main.py`).

**Evaluation Harness (distinct from tests):** `evaluation/eval_retrieval.py`, `evaluation/eval_llm.py`, `evaluation/generate_qa.py` implement offline quality evaluation (retrieval metrics, LLM answer scoring, synthetic Q&A generation) — these are model-quality gates, not correctness tests.

**E2E Tests:** Not used.

## Common Patterns

**Async Testing (recommended once adopted):**
```python
# Streaming generators return AsyncGenerator[str, None]:
@pytest.mark.asyncio
async def test_stream_answer():
    tokens = [t async for t in generator.stream_answer(query="q", context="c")]
    assert "".join(tokens)
```

**Error Testing (matches current fallback style):**
```python
# Library layer swallows errors and returns fallbacks — assert the fallback:
assert DenseRetriever().retrieve([...]) == []          # on Qdrant failure
# API layer raises HTTPException(500) — assert status_code via TestClient.
```

---

*Testing analysis: 2026-07-16*
