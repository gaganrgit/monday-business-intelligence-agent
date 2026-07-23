"""
Monday Business Intelligence Agent -- Streamlit frontend.

A simple chat UI that talks to the FastAPI backend over HTTP.
No business logic lives here -- this file is purely presentation.
"""

import os

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
REQUEST_TIMEOUT_SECONDS = 60

# Shared color theme so the dashboard/leaderboard visuals match the
# rest of the app's look and feel.
CHART_COLOR_SEQUENCE = px.colors.sequential.Teal
ACCENT_COLOR = "#0F9D8C"

EXAMPLE_QUESTIONS = [
    "How is our pipeline this quarter?",
    "Show active deals.",
    "How much revenue is expected?",
    "Give me a leadership update.",
    "What are the top business risks?",
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


@st.cache_data(ttl=120, show_spinner=False)
def call_dashboard_data_api() -> dict:
    """Fetch live analytics + leaderboard data from the backend.

    Cached for 2 minutes so navigating between tabs doesn't refetch
    from monday.com on every rerun; the sidebar "Refresh" button clears
    this cache on demand.
    """
    response = requests.get(f"{BACKEND_URL}/dashboard-data", timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


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

if "generating_for" not in st.session_state:
    st.session_state.generating_for = None


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
            st.rerun()

    st.divider()

    if st.button("📝 Generate Leadership Update", type="primary", use_container_width=True):
        with st.spinner("Generating leadership update..."):
            report = call_leadership_summary_api()
        st.session_state.chat_history.append({"role": "assistant", "content": report})
        st.rerun()

    st.divider()
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.generating_for = None
        st.session_state.pending_question = None
        st.rerun()

    st.divider()
    if st.button("🔄 Refresh Dashboard Data", use_container_width=True):
        call_dashboard_data_api.clear()
        st.rerun()

    st.divider()
    st.caption(f"Backend: {BACKEND_URL}")


# ----------------------------------------------------------------------
# Main chat area
# ----------------------------------------------------------------------

st.title("Founder Business Intelligence Assistant")
st.caption("Ask questions, explore live analytics, and see who's winning — all based on your Deals and Work Orders boards on monday.com.")

chat_tab, dashboard_tab, leaderboard_tab = st.tabs(["💬 Chat", "📊 Analytics Dashboard", "🏆 Leaderboard"])


# ----------------------------------------------------------------------
# Chat tab
# ----------------------------------------------------------------------

with chat_tab:
    # 1. Handle any pending question triggered from sidebar or example buttons
    if st.session_state.pending_question:
        question = st.session_state.pending_question
        st.session_state.pending_question = None
        st.session_state.chat_history.append({"role": "user", "content": question})
        st.session_state.generating_for = question
        st.rerun()

    # 2. Show starter container if chat history is empty
    if not st.session_state.chat_history and not st.session_state.generating_for:
        st.markdown("### 👋 Welcome to Founder Business Intelligence Assistant")
        st.markdown("Ask questions about your Deals and Work Orders, or select an example question below to get started.")

        st.subheader("💡 Example Questions")
        cols = st.columns(2)
        for idx, question in enumerate(EXAMPLE_QUESTIONS):
            col = cols[idx % 2]
            if col.button(f"👉 {question}", key=f"chat_example_{idx}", use_container_width=True):
                st.session_state.pending_question = question
                st.rerun()

        st.divider()

    # 3. Render chat history (User questions always render above assistant responses & input box)
    for entry in st.session_state.chat_history:
        with st.chat_message(entry["role"]):
            st.markdown(entry["content"])

    # 4. Handle response generation for active user question (so user prompt renders FIRST)
    if st.session_state.generating_for:
        prompt = st.session_state.generating_for
        st.session_state.generating_for = None
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                answer = call_chat_api(prompt)
            st.markdown(answer)
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        st.rerun()

    # 5. Chat input box (always placed at the bottom of the conversation)
    user_message = st.chat_input("Ask a question about your Deals or Work Orders...")
    if user_message:
        st.session_state.chat_history.append({"role": "user", "content": user_message})
        st.session_state.generating_for = user_message
        st.rerun()


# ----------------------------------------------------------------------
# Shared dashboard data loading (used by both Dashboard and Leaderboard tabs)
# ----------------------------------------------------------------------

def load_dashboard_payload():
    try:
        with st.spinner("Loading live data from monday.com..."):
            return call_dashboard_data_api(), None
    except requests.exceptions.RequestException:
        return None, "⚠️ Could not reach the backend service. Please make sure it is running."
    except requests.exceptions.HTTPError:
        return None, "⚠️ Failed to load dashboard data. Please try again."


# ----------------------------------------------------------------------
# Dashboard tab
# ----------------------------------------------------------------------

with dashboard_tab:
    payload, error = load_dashboard_payload()
    if error:
        st.warning(error)
    else:
        analytics = payload["analytics"]

        pipeline_open = analytics["total_pipeline_open"]
        pipeline_all = analytics["total_pipeline_all"]
        weighted = analytics["pipeline_by_probability"]
        billing = analytics["billing_summary"]
        receivables = analytics["pending_receivables"]
        delayed_wo = analytics["delayed_work_orders"]

        # --- KPI row -----------------------------------------------------
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Open Pipeline", f"₹{pipeline_open['total_value']:,.0f}", f"{pipeline_open['deal_count']} deals")
        k2.metric("Weighted Pipeline", f"₹{weighted['weighted_pipeline']:,.0f}")
        k3.metric("Total Invoiced", f"₹{billing['total_invoiced']:,.0f}")
        k4.metric("Pending Receivables", f"₹{receivables['total_receivable']:,.0f}")
        k5.metric("Delayed Work Orders", f"{len(delayed_wo)}")

        st.divider()

        # --- Revenue by sector + Deals by stage ---------------------------
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Revenue by Sector")
            sector_df = pd.DataFrame(analytics["revenue_by_sector"])
            if not sector_df.empty:
                fig = px.bar(
                    sector_df, x="sector", y="total_value", text="deal_count",
                    labels={"sector": "Sector", "total_value": "Deal Value (₹)"},
                    color="sector", color_discrete_sequence=CHART_COLOR_SEQUENCE,
                )
                fig.update_layout(showlegend=False, xaxis_title=None)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No sector data available.")

        with c2:
            st.subheader("Pipeline by Stage")
            stage_df = pd.DataFrame(analytics["deals_by_stage"])
            if not stage_df.empty:
                fig = px.bar(
                    stage_df, x="stage", y="total_value", text="deal_count",
                    labels={"stage": "Stage", "total_value": "Deal Value (₹)"},
                    color="stage", color_discrete_sequence=CHART_COLOR_SEQUENCE,
                )
                fig.update_layout(showlegend=False, xaxis_title=None)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No stage data available.")

        # --- Pipeline by probability + Work order execution status -------
        c3, c4 = st.columns(2)
        with c3:
            st.subheader("Pipeline by Closure Probability")
            bucket_df = pd.DataFrame(weighted["buckets"])
            if not bucket_df.empty:
                fig = px.pie(
                    bucket_df, names="probability_range", values="total_value", hole=0.45,
                    color_discrete_sequence=CHART_COLOR_SEQUENCE,
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No probability data available.")

        with c4:
            st.subheader("Work Order Execution Status")
            exec_df = pd.DataFrame(analytics["execution_summary"])
            if not exec_df.empty:
                fig = px.pie(
                    exec_df, names="status", values="count", hole=0.45,
                    color_discrete_sequence=CHART_COLOR_SEQUENCE,
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No work order status data available.")

        # --- Billing & Collections -----------------------------------------
        c5, c6 = st.columns(2)
        with c5:
            st.subheader("Billing Status")
            bill_df = pd.DataFrame(billing["by_status"])
            if not bill_df.empty:
                fig = px.bar(
                    bill_df, x="billing_status", y="total_amount", text="count",
                    labels={"billing_status": "Billing Status", "total_amount": "Amount (₹)"},
                    color="billing_status", color_discrete_sequence=CHART_COLOR_SEQUENCE,
                )
                fig.update_layout(showlegend=False, xaxis_title=None)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No billing data available.")

        with c6:
            st.subheader("Collection Status")
            collection_df = pd.DataFrame(analytics["collection_summary"])
            if not collection_df.empty:
                fig = px.bar(
                    collection_df, x="collection_status", y="total_amount", text="count",
                    labels={"collection_status": "Collection Status", "total_amount": "Amount (₹)"},
                    color="collection_status", color_discrete_sequence=CHART_COLOR_SEQUENCE,
                )
                fig.update_layout(showlegend=False, xaxis_title=None)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No collection data available.")

        # --- Upcoming closures + delayed work orders ------------------------
        c7, c8 = st.columns(2)
        with c7:
            st.subheader("Upcoming Deal Closures (30 days)")
            upcoming_df = pd.DataFrame(analytics["upcoming_closures"])
            if not upcoming_df.empty:
                st.dataframe(upcoming_df, use_container_width=True, hide_index=True)
            else:
                st.info("No deals expected to close in the next 30 days.")

        with c8:
            st.subheader("Delayed Work Orders")
            delayed_df = pd.DataFrame(delayed_wo)
            if not delayed_df.empty:
                st.dataframe(delayed_df, use_container_width=True, hide_index=True)
            else:
                st.success("No delayed work orders. 🎉")


# ----------------------------------------------------------------------
# Leaderboard tab
# ----------------------------------------------------------------------

with leaderboard_tab:
    payload, error = load_dashboard_payload()
    if error:
        st.warning(error)
    else:
        lb = payload["leaderboards"]
        st.caption("Rankings are computed live from your Deals and Work Orders boards.")

        l1, l2 = st.columns(2)
        with l1:
            st.subheader("🥇 Top Customers by Deal Value")
            df = pd.DataFrame(lb["top_customers"])
            if not df.empty:
                st.dataframe(
                    df.rename(columns={"customer_code": "Customer", "total_deal_value": "Total Deal Value (₹)"}),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("No customer data available.")

        with l2:
            st.subheader("🏭 Top Sectors by Revenue")
            df = pd.DataFrame(lb["top_sectors"])
            if not df.empty:
                st.dataframe(
                    df.rename(columns={"sector": "Sector", "total_value": "Total Value (₹)", "deal_count": "Deals"}),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("No sector data available.")

        l3, l4 = st.columns(2)
        with l3:
            st.subheader("💎 Largest Individual Deals")
            df = pd.DataFrame(lb["largest_deals"])
            if not df.empty:
                st.dataframe(
                    df.rename(columns={
                        "deal_name": "Deal", "client_code": "Customer", "sector": "Sector",
                        "deal_status": "Status", "deal_value": "Deal Value (₹)",
                    }),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("No deal data available.")

        with l4:
            st.subheader("🎯 Top Performers (Deal Owners)")
            df = pd.DataFrame(lb["top_performers"])
            if not df.empty:
                st.dataframe(
                    df.rename(columns={"owner_code": "Owner", "total_deal_value": "Total Deal Value (₹)"}),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("No owner data available.")

        l5, l6 = st.columns(2)
        with l5:
            st.subheader("🧾 Top Customers by Billing")
            df = pd.DataFrame(lb["top_billing_customers"])
            if not df.empty:
                st.dataframe(
                    df.rename(columns={"customer_code": "Customer", "total_invoiced": "Total Invoiced (₹)"}),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("No billing data available.")

        with l6:
            st.subheader("⏳ Highest Outstanding Receivables")
            df = pd.DataFrame(lb["top_receivables"])
            if not df.empty:
                st.dataframe(
                    df.rename(columns={"customer_code": "Customer", "total_receivable": "Receivable (₹)"}),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.success("No outstanding receivables. 🎉")