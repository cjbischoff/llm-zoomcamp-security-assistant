"""Streamlit UI for security threat intelligence RAG.

Real API-backed client (INT-04 / D-03): consumes the ``/query`` streaming
response token-by-token via a synchronous ``httpx`` client, captures the
``X-Query-Id`` header for feedback, renders a sources/citations panel, and
fails visibly (SC4) with fixed friendly copy when the API is down — never a
static placeholder answer or a fake feedback toast (both prohibited by the
UI-SPEC).
"""

import re

import streamlit as st
import httpx
from dotenv import load_dotenv

load_dotenv()

# --- Copy constants (UI-SPEC Copywriting Contract) ------------------------
SPINNER_MSG = "Searching the knowledge base…"
EMPTY_SUBMIT_MSG = "Enter a security question to search."
API_DOWN_MSG = (
    "⚠️ Couldn't reach the API. The service may be down or the API URL may be "
    "wrong — check that the FastAPI server is running, then try again."
)
QUERY_FAILED_MSG = "The query failed (server error). Try again in a moment."
NO_CITATIONS_MSG = "No source passage cleared the relevance threshold for this query."
FEEDBACK_SUCCESS_MSG = "Thanks — feedback recorded."
FEEDBACK_FAILURE_MSG = "Couldn't record feedback — the API may be down."

# Grounding-gate refusal sentinels the pipeline emits (rag/pipeline.py). When the
# streamed answer is one of these, the corpus did not cover the question, so the
# sources panel shows the refusal notice instead of citations — never fabricated.
_REFUSAL_MARKERS = (
    "isn't covered in the indexed sources",
    "knowledge base collection is not available",
    "Retrieval backend is unavailable",
)

# Threat-ID families surfaced inline in answers (OWASP LLM/Agentic, MCP, NIST).
# Used only to lift IDs the answer already cites — the UI never invents citations.
_THREAT_ID_RE = re.compile(
    r"\b(?:LLM\d{2}|AGENTIC-\d+|ASI-\d+|MCP-[A-Za-z0-9-]+|NIST(?:[- ][A-Za-z0-9.]+)+)\b"
)

# Page config
st.set_page_config(
    page_title="Security Threat Intelligence RAG",
    page_icon="🔒",
    layout="wide",
)

# Title
st.title("🔒 Security Threat Intelligence RAG")
st.markdown(
    "Query across OWASP, NIST, and MCP security documentation for threat intelligence."
)

# Sidebar
with st.sidebar:
    st.header("Settings")
    prompt_variant = st.radio(
        "Prompt Variant",
        ["base", "practitioner"],
        index=1,
        help="Base: Simple answers | Practitioner: Structured with threat IDs, "
        "risk levels, mitigations",
    )
    retrieval_mode = st.selectbox(
        "Retrieval Mode",
        ["dense", "hybrid", "hybrid_rerank"],
        index=2,
        help="How passages are retrieved. hybrid_rerank is the default (eval winner).",
    )
    api_url = st.text_input("API URL", value="http://localhost:8000")

# Main content
col1, col2 = st.columns([3, 1])

with col1:
    user_id = st.text_input("User ID (optional)", placeholder="your-id")
    query = st.text_area(
        "Enter your security question",
        placeholder="e.g., What are the top LLM vulnerabilities? "
        "How do I prevent prompt injection?",
        height=100,
    )

with col2:
    st.info(
        "**Example Queries:**\n"
        "- What is prompt injection?\n"
        "- How do I prevent training data poisoning?\n"
        "- Explain the MCP security model\n"
        "- What does NIST AI RMF cover?\n\n"
        "Try one of the example questions, or ask your own security question above."
    )


def _stream_answer(payload: dict):
    """Yield answer tokens from a real ``/query`` stream, capturing the query id.

    Opens a synchronous ``httpx`` stream against ``POST /query`` (Streamlit is
    synchronous — no AsyncClient). The ``X-Query-Id`` response header is
    available the instant the stream context opens, before the first body byte,
    so it is stashed into ``st.session_state`` for feedback before any token is
    yielded. Transport/HTTP failures propagate out of the generator so the
    caller's ``try/except`` around ``st.write_stream`` surfaces the SC4 states.

    Args:
        payload: The ``/query`` JSON body (query, prompt_variant, retrieval_mode,
            user_id).

    Yields:
        str: Decoded answer text chunks as they arrive from the API.
    """
    with httpx.Client(timeout=60.0) as client:
        with client.stream("POST", f"{api_url}/query", json=payload) as response:
            response.raise_for_status()
            # Header is populated on context entry, before body bytes.
            st.session_state["query_id"] = response.headers.get("x-query-id")
            for chunk in response.iter_text():
                yield chunk


def _render_sources(answer: str) -> None:
    """Render the sources/citations panel for a completed answer.

    The ``/query`` endpoint streams ``text/plain`` answer tokens only — it does
    not return a structured source list — so this presents the citations the
    answer itself surfaces (threat-ID chips lifted from the answer text) and
    never fabricates a source. A grounding-gate refusal renders the fixed
    "no relevant passage" notice instead of citations.

    Args:
        answer: The full streamed answer text returned by ``st.write_stream``.
    """
    st.subheader("Sources")
    with st.container(border=True):
        if any(marker in answer for marker in _REFUSAL_MARKERS):
            st.info(NO_CITATIONS_MSG)
            return

        # Ordered de-dup of threat IDs the answer already cites.
        threat_ids = list(dict.fromkeys(_THREAT_ID_RE.findall(answer)))
        if threat_ids:
            st.caption("Threat IDs cited: " + "  ".join(f"`{tid}`" for tid in threat_ids))
            for tid in threat_ids:
                with st.expander(tid, expanded=False):
                    st.caption(
                        "Cited inline in the answer above. The API streams the "
                        "answer text; per-passage source detail is not returned "
                        "separately in this build."
                    )
        else:
            st.caption("Citations are inline in the answer above.")


# Submit button — the single primary CTA (UI-SPEC: accent reserved for it).
if st.button("🔍 Ask", type="primary", use_container_width=True):
    if not query.strip():
        # Empty submit: show error, send no request, render nothing else.
        st.error(EMPTY_SUBMIT_MSG)
    else:
        # New question invalidates any prior answer's id/vote state.
        st.session_state.pop("query_id", None)
        payload = {
            "query": query,
            "prompt_variant": prompt_variant,
            "retrieval_mode": retrieval_mode,
            "user_id": user_id or None,
        }
        try:
            st.subheader("Answer")
            with st.spinner(SPINNER_MSG):
                answer = st.write_stream(_stream_answer(payload))
            _render_sources(answer)
        except (httpx.ConnectError, httpx.TimeoutException):
            # SC4: API down / unreachable — visible red error, no answer/sources.
            st.session_state.pop("query_id", None)
            st.error(API_DOWN_MSG)
        except httpx.HTTPStatusError:
            # Non-2xx from /query — friendly copy, never raw exception text.
            st.session_state.pop("query_id", None)
            st.error(QUERY_FAILED_MSG)

def _post_feedback(query_id: str, rating: int) -> None:
    """POST a thumbs vote to ``/feedback`` and confirm only on a real 2xx.

    Shows the success copy only when the API returns a 2xx (the scaffold's fake
    success toast is prohibited); any non-2xx or transport failure shows the
    fixed failure copy and leaves the buttons active to retry. On success the
    vote is recorded in ``st.session_state`` keyed by ``query_id`` so the
    controls hide for the current answer. Raw exception text is never rendered.

    Args:
        query_id: The id returned by ``/query`` for the answered question.
        rating: +1 for Helpful, -1 for Not helpful (the API bounds this to a
            Literal[-1, 1] at the trust boundary).
    """
    try:
        response = httpx.post(
            f"{api_url}/feedback",
            json={"query_id": query_id, "rating": rating},
            timeout=10.0,
        )
        response.raise_for_status()
    except (httpx.HTTPStatusError, httpx.TransportError):
        st.error(FEEDBACK_FAILURE_MSG)
        return
    st.session_state.setdefault("voted", {})[query_id] = True
    st.success(FEEDBACK_SUCCESS_MSG)


# Feedback region — appears only after a successful answer with a real query_id.
_query_id = st.session_state.get("query_id")
if _query_id and not st.session_state.get("voted", {}).get(_query_id):
    st.subheader("Was this helpful?")
    fb_col1, fb_col2 = st.columns(2)
    with fb_col1:
        if st.button("👍 Helpful", use_container_width=True):
            _post_feedback(_query_id, 1)
    with fb_col2:
        if st.button("👎 Not helpful", use_container_width=True):
            _post_feedback(_query_id, -1)

# Footer
st.divider()
st.markdown(
    "**Security RAG System** | Capstone Project for LLM Zoomcamp\n\n"
    "Corpus: OWASP LLM Top 10 | OWASP Agentic Top 10 | MCP Security | NIST AI RMF"
)
