"""
Business analytics engine.

Simple, composable Python functions that turn cleaned Deals / Work
Orders DataFrames into business metrics. Each function returns plain
JSON-serializable Python types (dict/list/str/float) so the result can
be dropped straight into the summary object sent to the LLM.

No function here ever raises on empty input -- an empty board simply
produces zeroed-out / empty metrics.
"""

from datetime import date, timedelta
from typing import Any, Dict, List

import pandas as pd

from backend.app.logger import get_logger

logger = get_logger(__name__)

# Statuses that are definitively closed (case-insensitive match after normalize_text).
# Open pipeline = everything that is NOT in this exclusion set.
# Override via the CLOSED_DEAL_STATUSES env var (comma-separated).
import os as _os

_env_closed = _os.getenv("CLOSED_DEAL_STATUSES", "")
if _env_closed.strip():
    CLOSED_DEAL_STATUSES: set = {s.strip().title() for s in _env_closed.split(",") if s.strip()}
else:
    CLOSED_DEAL_STATUSES = {
        "Won", "Closed Won", "Closed", "Lost", "Closed Lost",
        "Dead", "Rejected", "Cancelled", "Canceled",
    }

DELAYED_STATUSES = {"Delayed", "Overdue", "Late"}


# ----------------------------------------------------------------------
# Deals analytics
# ----------------------------------------------------------------------

def total_pipeline_value(deals_df: pd.DataFrame, only_open: bool = True) -> Dict[str, Any]:
    if deals_df.empty:
        return {"total_value": 0.0, "deal_count": 0, "only_open": only_open}

    df = deals_df
    if only_open and "deal_status" in df.columns:
        # Exclusion approach: open = anything that is NOT a known closed/lost status.
        # This is more robust than a whitelist because it works across custom board setups.
        df = df[~df["deal_status"].isin(CLOSED_DEAL_STATUSES)]

    total = float(df["deal_value"].sum()) if "deal_value" in df.columns else 0.0
    return {
        "total_value": round(total, 2),
        "deal_count": int(len(df)),
        "only_open": only_open,
    }


def revenue_by_sector(deals_df: pd.DataFrame) -> List[Dict[str, Any]]:
    if deals_df.empty or "sector" not in deals_df.columns:
        return []
    grouped = (
        deals_df.groupby("sector")["deal_value"]
        .agg(["sum", "count"])
        .reset_index()
        .sort_values("sum", ascending=False)
    )
    return [
        {"sector": row["sector"] or "Unspecified", "total_value": round(float(row["sum"]), 2), "deal_count": int(row["count"])}
        for _, row in grouped.iterrows()
    ]


def deals_by_stage(deals_df: pd.DataFrame) -> List[Dict[str, Any]]:
    if deals_df.empty or "deal_stage" not in deals_df.columns:
        return []
    grouped = (
        deals_df.groupby("deal_stage")["deal_value"]
        .agg(["sum", "count"])
        .reset_index()
        .sort_values("sum", ascending=False)
    )
    return [
        {"stage": row["deal_stage"] or "Unspecified", "total_value": round(float(row["sum"]), 2), "deal_count": int(row["count"])}
        for _, row in grouped.iterrows()
    ]


def pipeline_by_probability(deals_df: pd.DataFrame) -> Dict[str, Any]:
    if deals_df.empty or "closure_probability" not in deals_df.columns:
        return {"weighted_pipeline": 0.0, "buckets": []}

    df = deals_df.copy()
    df["weighted_value"] = df["deal_value"] * (df["closure_probability"].clip(0, 100) / 100.0)

    bins = [0, 25, 50, 75, 100]
    labels = ["0-25%", "26-50%", "51-75%", "76-100%"]
    df["bucket"] = pd.cut(df["closure_probability"], bins=bins, labels=labels, include_lowest=True)

    buckets = (
        df.groupby("bucket", observed=True)["deal_value"]
        .agg(["sum", "count"])
        .reset_index()
    )
    bucket_list = [
        {"probability_range": str(row["bucket"]), "total_value": round(float(row["sum"]), 2), "deal_count": int(row["count"])}
        for _, row in buckets.iterrows()
    ]
    return {
        "weighted_pipeline": round(float(df["weighted_value"].sum()), 2),
        "buckets": bucket_list,
    }


def upcoming_closures(deals_df: pd.DataFrame, days_ahead: int = 30) -> List[Dict[str, Any]]:
    if deals_df.empty:
        return []
    today = date.today()
    horizon = today + timedelta(days=days_ahead)

    df = deals_df.copy()
    df["effective_close_date"] = df["close_date"].fillna(df.get("tentative_close_date"))
    upcoming = df[
        df["effective_close_date"].notna()
        & (df["effective_close_date"] >= today)
        & (df["effective_close_date"] <= horizon)
    ]
    upcoming = upcoming.sort_values("effective_close_date")

    return [
        {
            "deal_name": row["deal_name"],
            "client_code": row.get("client_code", ""),
            "expected_close_date": str(row["effective_close_date"]),
            "deal_value": round(float(row["deal_value"]), 2),
            "sector": row.get("sector", ""),
        }
        for _, row in upcoming.iterrows()
    ]


# ----------------------------------------------------------------------
# Work order analytics
# ----------------------------------------------------------------------

def delayed_work_orders(wo_df: pd.DataFrame) -> List[Dict[str, Any]]:
    if wo_df.empty:
        return []
    today = date.today()

    df = wo_df.copy()
    status_delayed = df["execution_status"].isin(DELAYED_STATUSES) if "execution_status" in df.columns else pd.Series(False, index=df.index)
    past_due = (
        df["end_date"].notna()
        & (df["end_date"] < today)
        & (~df["execution_status"].isin({"Completed", "Closed", "Done"}))
    ) if "end_date" in df.columns else pd.Series(False, index=df.index)

    delayed = df[status_delayed | past_due]

    return [
        {
            "deal_name": row["deal_name"],
            "customer_code": row.get("customer_code", ""),
            "execution_status": row.get("execution_status", ""),
            "end_date": str(row["end_date"]) if pd.notna(row.get("end_date")) else None,
            "sector": row.get("sector", ""),
        }
        for _, row in delayed.iterrows()
    ]


def execution_summary(wo_df: pd.DataFrame) -> List[Dict[str, Any]]:
    if wo_df.empty or "execution_status" not in wo_df.columns:
        return []
    counts = wo_df["execution_status"].replace("", "Unspecified").value_counts()
    return [{"status": status, "count": int(count)} for status, count in counts.items()]


def billing_summary(wo_df: pd.DataFrame) -> Dict[str, Any]:
    if wo_df.empty:
        return {"total_invoiced": 0.0, "by_status": []}

    total_invoiced = float(wo_df["invoice_amount"].sum()) if "invoice_amount" in wo_df.columns else 0.0
    by_status = []
    if "billing_status" in wo_df.columns:
        grouped = wo_df.groupby("billing_status")["invoice_amount"].agg(["sum", "count"]).reset_index()
        by_status = [
            {
                "billing_status": row["billing_status"] or "Unspecified",
                "total_amount": round(float(row["sum"]), 2),
                "count": int(row["count"]),
            }
            for _, row in grouped.iterrows()
        ]
    return {"total_invoiced": round(total_invoiced, 2), "by_status": by_status}


def pending_receivables(wo_df: pd.DataFrame) -> Dict[str, Any]:
    if wo_df.empty or "amount_receivable" not in wo_df.columns:
        return {"total_receivable": 0.0, "records": []}

    df = wo_df[wo_df["amount_receivable"] > 0]
    records = [
        {
            "deal_name": row["deal_name"],
            "customer_code": row.get("customer_code", ""),
            "amount_receivable": round(float(row["amount_receivable"]), 2),
            "collection_status": row.get("collection_status", ""),
        }
        for _, row in df.iterrows()
    ]
    return {
        "total_receivable": round(float(df["amount_receivable"].sum()), 2),
        "records": records[:50],  # cap payload size sent to LLM
        "record_count": len(records),
    }


def collection_summary(wo_df: pd.DataFrame) -> List[Dict[str, Any]]:
    if wo_df.empty or "collection_status" not in wo_df.columns:
        return []
    grouped = wo_df.groupby("collection_status")["amount_receivable"].agg(["sum", "count"]).reset_index()
    return [
        {
            "collection_status": row["collection_status"] or "Unspecified",
            "total_amount": round(float(row["sum"]), 2),
            "count": int(row["count"]),
        }
        for _, row in grouped.iterrows()
    ]


# ----------------------------------------------------------------------
# Cross-board analytics
# ----------------------------------------------------------------------

def cross_board_customer_lookup(deals_df: pd.DataFrame, wo_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Find customers who have both an active deal AND a delayed work order."""
    if deals_df.empty or wo_df.empty:
        return []

    active_deals = deals_df[deals_df["deal_status"].isin(OPEN_DEAL_STATUSES)] if "deal_status" in deals_df.columns else deals_df
    active_customers = set(active_deals["client_code"].dropna()) if "client_code" in active_deals.columns else set()

    delayed = delayed_work_orders(wo_df)
    delayed_customers = {d["customer_code"] for d in delayed if d.get("customer_code")}

    overlap = active_customers.intersection(delayed_customers)
    results = []
    for customer in overlap:
        if not customer:
            continue
        customer_deals = active_deals[active_deals["client_code"] == customer]
        customer_delays = [d for d in delayed if d.get("customer_code") == customer]
        results.append({
            "customer_code": customer,
            "active_deal_count": int(len(customer_deals)),
            "active_deal_value": round(float(customer_deals["deal_value"].sum()), 2),
            "delayed_work_order_count": len(customer_delays),
        })
    return results


def filter_by_sector(df: pd.DataFrame, sector: str) -> pd.DataFrame:
    """Case-insensitive sector filter, safe for empty/missing columns."""
    if df.empty or "sector" not in df.columns or not sector:
        return df
    return df[df["sector"].str.lower() == sector.lower()]


def filter_by_quarter(deals_df: pd.DataFrame, quarter: int, year: int) -> pd.DataFrame:
    """Filter deals to those whose effective close date falls in the given quarter/year.

    Uses the first available date column: close_date → tentative_close_date → created_date.
    Returns the original DataFrame unmodified if no date columns are available.
    """
    if deals_df.empty or quarter not in (1, 2, 3, 4):
        return deals_df

    q_start_month = (quarter - 1) * 3 + 1
    q_end_month = q_start_month + 2
    q_start = date(year, q_start_month, 1)
    import calendar as _cal
    q_end = date(year, q_end_month, _cal.monthrange(year, q_end_month)[1])

    df = deals_df.copy()

    # Build effective date: first non-null of close_date, tentative_close_date, created_date
    date_cols = [c for c in ("close_date", "tentative_close_date", "created_date") if c in df.columns]
    if not date_cols:
        return deals_df

    df["_eff_date"] = None
    for col in date_cols:
        df["_eff_date"] = df["_eff_date"].where(df["_eff_date"].notna(), df[col])

    mask = df["_eff_date"].notna() & (df["_eff_date"] >= q_start) & (df["_eff_date"] <= q_end)
    filtered = deals_df[mask.values]
    return filtered if not filtered.empty else deals_df  # fall back to all data if nothing in range
