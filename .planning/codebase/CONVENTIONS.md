# Coding Conventions

**Analysis Date:** 2026-07-16

## Naming Patterns

**Files:**
- `snake_case.py` for all modules (`rag/pipeline.py`, `ingestion/transforms/chunk.py`)
- Package dirs are lowercase single words (`rag/`, `api/`, `ingestion/`, `monitoring/`, `evaluation/`, `ui/`)
- Each package has an `__init__.py` (currently empty markers)
- dlt source modules named by data source (`ingestion/dlt_sources/owasp_llm.py`, `nist_ai_rmf.py`)

**Functions/Methods:**
- `snake_case` (`stream_answer`, `log_query`, `chunk_by_sections`, `normalize_threat_id`)
- Async functions prefixed conceptually by streaming intent (`stream_answer`, `answer_generator`)
- Private helpers prefixed with `_` (`_init_tables`)

**Variables:**
- `snake_case` (`retrieval_latency_ms`, `prompt_variant`, `query_lower`)
- Latency/measurement vars carry unit suffix (`_ms`) — `retrieval_latency_ms`, `total_latency_ms`

**Types/Classes:**
- `PascalCase` (`RAGPipeline`, `HybridRetriever`, `QueryLogger`, `LLMGenerator`, `Chunker`)
- Pydantic models use noun + role suffix (`QueryRequest`, `HealthResponse` in `api/main.py`)
- Class-level constants `UPPER_SNAKE` (`THREAT_MAPPINGS` in `rag/rewriter.py`)

## Code Style

**Formatting:**
- No formatter configured (no `pyproject.toml`, `ruff.toml`, `.flake8`, `setup.cfg` present)
- De facto 4-space indent, double-quoted strings, ~100 char lines
- Multi-line function signatures with one arg per line when long (`RAGPipeline.stream_answer`, `QueryLogger.log_query`)

**Linting:**
- Not detected — no linter config in repo. Recommend adding `ruff` before growth.

## Import Organization

**Order (observed, not enforced):**
1. Stdlib (`os`, `time`, `json`, `asyncio`, `logging`, `re`, `csv`, `datetime`)
2. Typing (`from typing import ...`)
3. Third-party (`from openai import AsyncOpenAI`, `from fastapi import ...`, `from qdrant_client import QdrantClient`)
4. First-party absolute (`from rag.rewriter import QueryRewriter`)

**Path Aliases:**
- None. Absolute package imports from repo root (`rag.pipeline`, `monitoring.logging`).
- Lazy imports used inside route handlers to avoid circular deps (`api/main.py` imports `RAGPipeline` inside `query_endpoint`). Note the comment `# lazy import to avoid circular dependencies`.

## Error Handling

**Patterns:**
- Broad `try/except Exception as e` around external calls (OpenAI, Qdrant, route handlers)
- Two divergent styles — reconcile before scaling:
  - **API layer** (`api/main.py`): log via `logger.error(...)` then `raise HTTPException(status_code=500, detail=str(e))`
  - **Library layer** (`rag/`, `monitoring/`): swallow the error and return a fallback — `return []` (`DenseRetriever.retrieve`), or `yield f"Error generating answer: {str(e)}"` (`LLMGenerator.stream_answer`)
- `ValueError` raised for invalid enum-like input (`raise ValueError(f"Unknown prompt variant: {prompt_variant}")` in `rag/generator.py`)
- Existence checks before file reads (`evaluation/eval_retrieval.py` `load_ground_truth`)

## Logging

**Framework:** stdlib `logging`. `logging.basicConfig(level=logging.INFO)` set once in `api/main.py`; modules use `logger = logging.getLogger(__name__)`.

**Patterns:**
- Module-level `logger` per file (`monitoring/logging.py`, `api/main.py`)
- Structured payloads logged as JSON strings (`logger.info(f"Query logged: {json.dumps(log_entry)}")`)
- Some library code uses `print(...)` for errors (`DenseRetriever.retrieve`, `evaluation/eval_retrieval.py`) — inconsistent with the logging convention; prefer `logger` in new code.

## Comments

**When to Comment:**
- Inline comments flag placeholders/stubs heavily (`# Placeholder: would write to postgres`, `# Would be populated from actual retriever`). These mark unfinished integration points.
- Step comments narrate pipeline flow (`# Step 1: Rewrite query` ... `# Step 4: Log query`)

**Docstrings:**
- Every module opens with a one-line `"""..."""` module docstring
- Every class and public method has a docstring; some are full multi-line with behavior notes (`LLMGenerator.stream_answer` documents prompt variants), many are one-liners
- Not Google-style structured (no `Args:`/`Returns:`/`Raises:` sections). New public functions should adopt Google-style docstrings per project standard.

## Function Design

**Size:** Small, single-purpose methods (mostly <40 lines).

**Parameters:**
- Keyword args with defaults for optional config (`top_k: int = 5`, `prompt_variant: str = "base"`, `user_id: str = None`)
- Type hints on all params and returns (`List[Dict[str, Any]]`, `AsyncGenerator[str, None]`, `Tuple[str, str]`)
- Note: `user_id: str = None` uses `None` default without `Optional[...]` in some signatures (`api/main.py`, `rag/pipeline.py`); `monitoring/logging.py` correctly uses `Optional[str]`. Prefer `Optional[...]` for None-defaulted params.

**Return Values:**
- Retrievers/chunkers return `List[Dict[str, Any]]` with `{"text", "score", "metadata"}` or `{"text", "metadata"}` shape
- Streaming generators `yield` string tokens
- Config read from env with defaults (`os.getenv("QDRANT_PORT", 6333)`, `os.getenv("QDRANT_COLLECTION_NAME", "security_rag")`)

## Module Design

**Exports:** No `__all__` declarations. All `__init__.py` files are empty markers — import from submodules directly.

**Barrel Files:** Not used.

**Static methods:** Utility classes group related `@staticmethod` functions (`Chunker`, `RetrieverEvaluator`) rather than module-level functions.

---

*Convention analysis: 2026-07-16*
