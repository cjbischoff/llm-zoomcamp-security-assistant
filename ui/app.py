"""Streamlit UI for security threat intelligence RAG"""

import streamlit as st
import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

# Page config
st.set_page_config(
    page_title="Security Threat Intelligence RAG",
    page_icon="🔒",
    layout="wide"
)

# Title
st.title("🔒 Security Threat Intelligence RAG")
st.markdown("""
Query across OWASP, NIST, and MCP security documentation for threat intelligence.
""")

# Sidebar
with st.sidebar:
    st.header("Settings")
    prompt_variant = st.radio(
        "Prompt Variant",
        ["base", "practitioner"],
        help="Base: Simple answers | Practitioner: Structured with threat IDs, risk levels, mitigations"
    )
    api_url = st.text_input("API URL", value="http://localhost:8000")

# Main content
col1, col2 = st.columns([3, 1])

with col1:
    user_id = st.text_input("User ID (optional)", placeholder="your-id")
    query = st.text_area(
        "Enter your security question",
        placeholder="e.g., What are the top LLM vulnerabilities? How do I prevent prompt injection?",
        height=100
    )

with col2:
    st.info("""
    **Example Queries:**
    - What is prompt injection?
    - How do I prevent training data poisoning?
    - Explain the MCP security model
    - What does NIST AI RMF cover?
    """)

# Submit button
if st.button("🔍 Query", type="primary", use_container_width=True):
    if not query.strip():
        st.error("Please enter a question")
    else:
        try:
            # Stream response
            st.subheader("Response:")
            response_container = st.empty()
            full_response = ""

            # Simulate streaming (in production, would use actual API streaming)
            with st.spinner("Searching knowledge base..."):
                try:
                    async def query_api():
                        """Query the API"""
                        async with httpx.AsyncClient() as client:
                            response = await client.post(
                                f"{api_url}/query",
                                json={
                                    "query": query,
                                    "prompt_variant": prompt_variant,
                                    "user_id": user_id or None
                                },
                                timeout=30.0
                            )
                            return response.text

                    # For demonstration, show placeholder
                    st.write("""
                    ### Answer

                    The system would retrieve relevant security documentation and generate a response here.

                    **Features:**
                    - Semantic search across OWASP, NIST, MCP sources
                    - LLM-powered synthesis with threat context
                    - Threat ID normalization for accurate retrieval
                    - Structured answers with mitigations and controls
                    """)

                except Exception as api_error:
                    st.warning(f"API Error: {api_error}\n\nMake sure the FastAPI server is running: `python api/main.py`")

        except Exception as e:
            st.error(f"Error: {str(e)}")

# Feedback section
st.divider()
st.subheader("Feedback")
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("👍 Helpful"):
        st.success("Thank you for your feedback!")

with col2:
    if st.button("😐 Neutral"):
        st.info("Feedback recorded")

with col3:
    if st.button("👎 Not Helpful"):
        st.warning("We'll improve this response")

# Footer
st.divider()
st.markdown("""
---
**Security RAG System** | Capstone Project for LLM Zoomcamp

Corpus: OWASP LLM Top 10 | OWASP Agentic Top 10 | MCP Security | NIST AI RMF

[GitHub](https://github.com/yourusername/llm-zoomcamp-security-assistant) | [Docs](./README.md)
""")
