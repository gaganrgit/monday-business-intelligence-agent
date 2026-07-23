"""
Monday Business Intelligence Agent -- Streamlit frontend.

A simple chat UI that talks to the FastAPI backend over HTTP.
No business logic lives here -- this file is purely presentation.
"""

import os

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
REQUEST_TIMEOUT_SECONDS = 60

EXAMPLE_QUESTIONS = [
    "How is our pipeline this quarter?",
    "Which sector performs best?",
    "How much revenue is expected?",
    "Show delayed work orders.",
    "Which customers have active deals and delayed work orders?",
    "Show pending receivables.",
    "Show billing summary.",
]

st.set_page_config(page_title="Monday BI Agent", page_icon="📊", layout="wide")


def call_chat_api(message: str) -> str:
    try:
        response = requests.post(
            f"{BACKEND_URL}/chat", json={"message": message}, timeout=REQUEST_TIMEOUT_SECONDS
        )
    except requests.exceptions.RequestException:
        return "⚠️ Could not reach the backend service. Please make sure it is running."

    if response.status_code != 200:
        try:
            detail = response.json().get("detail", "Unknown error.")
        except ValueError:
            detail = "Unknown error."
        return f"⚠️ {detail}"

    return response.json().get("answer", "No answer returned.")


def call_leadership_summary_api() -> str:
    try:
        response = requests.get(f"{BACKEND_URL}/leadership-summary", timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.exceptions.RequestException:
        return "⚠️ Could not reach the backend service. Please make sure it is running."

    if response.status_code != 200:
        return "⚠️ Failed to generate the leadership summary. Please try again."

    return response.text


# ----------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # list of {"role": "user"|"assistant", "content": str}

if "pending_question" not in st.session_state:
    st.session_state.pending_question = None


# ----------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------

with st.sidebar:
    st.header("📊 Monday BI Agent")
    st.caption("Founder-level insights, live from monday.com")

    st.subheader("Example Questions")
    for question in EXAMPLE_QUESTIONS:
        if st.button(question, key=f"example_{question}", use_container_width=True):
            st.session_state.pending_question = question

    st.divider()

    if st.button("📝 Generate Leadership Update", type="primary", use_container_width=True):
        with st.spinner("Generating leadership update..."):
            report = call_leadership_summary_api()
        st.session_state.chat_history.append({"role": "assistant", "content": report})

    st.divider()
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

    st.divider()
    st.caption(f"Backend: {BACKEND_URL}")


# ----------------------------------------------------------------------
# Main chat area
# ----------------------------------------------------------------------

st.title("Founder Business Intelligence Assistant")
st.caption("Ask questions about your Deals and Work Orders boards on monday.com — answers are always based on live data.")

# Render chat history
for entry in st.session_state.chat_history:
    with st.chat_message(entry["role"]):
        st.markdown(entry["content"])

# Handle a question triggered by an example button
if st.session_state.pending_question:
    question = st.session_state.pending_question
    st.session_state.pending_question = None
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.spinner("Thinking..."):
        answer = call_chat_api(question)
    st.session_state.chat_history.append({"role": "assistant", "content": answer})
    st.rerun()

# Chat input
user_message = st.chat_input("Ask a question about your Deals or Work Orders...")
if user_message:
    st.session_state.chat_history.append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.markdown(user_message)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer = call_chat_api(user_message)
        st.markdown(answer)

    st.session_state.chat_history.append({"role": "assistant", "content": answer})
