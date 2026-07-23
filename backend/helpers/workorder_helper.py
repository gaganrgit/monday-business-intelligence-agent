"""
backend/helpers/workorder_helper.py

Deterministic work-order KPI computation from the cleaned Work Orders DataFrame.
No LLM calls. All arithmetic is Python / pandas.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

import pandas as pd

from backend.helpers.calculation_helper import (
    calculate_average,
    calculate_count,
    calculate_sum,
    format_currency,
    group_count,
    group_sum,
    rank_by_sum,
    safe_numeric,
    top_n,
)

# ---------------------------------------------------------------------------
# Column names
# ---------------------------------------------------------------------------
EXEC_STATUS_COL = "execution_status"
BILLING_STATUS_COL = "billing_status"
COLLECTION_STATUS_COL = "collection_status"
INVOICE_COL = "invoice_amount"
RECEIVABLE_COL = "amount_receivable"
CUSTOMER_COL = "customer_code"
SECTOR_COL = "sector"
END_DATE_COL = "end_date"

DELAYED_STATUSES = {"Delayed", "Overdue", "Late"}
COMPLETED_STATUSES = {"Completed", "Closed", "Done"}
OPEN_EXEC_STATUSES = {"In Progress", "Ongoing", "Active", "Pending", "Started"}


def compute_workorder_kpis(df: pd.DataFrame) -> Dict[str, Any]:
    """Return a comprehensive work-order KPI dict from the cleaned DataFrame."""
    if df.empty:
        return _empty_workorder_kpis()

    today = date.today()

    # --- Execution summary ---
    exec_counts = group_count(df, EXEC_STATUS_COL) if EXEC_STATUS_COL in df.columns else {}
    delayed_count = sum(v for k, v in exec_counts.items() if k in DELAYED_STATUSES)
    completed_count = sum(v for k, v in exec_counts.items() if k in COMPLETED_STATUSES)
    open_count = sum(v for k, v in exec_counts.items() if k in OPEN_EXEC_STATUSES)

    # Past-due: end_date in the past and not completed
    past_due_count = 0
    delayed_records: List[Dict] = []
    if END_DATE_COL in df.columns and EXEC_STATUS_COL in df.columns:
        past_due_mask = (
            df[END_DATE_COL].notna()
            & (df[END_DATE_COL].apply(lambda x: x < today if x else False))
            & (~df[EXEC_STATUS_COL].isin(COMPLETED_STATUSES))
        )
        past_due_df = df[past_due_mask]
        past_due_count = len(past_due_df)
        delayed_records = _build_delayed_records(past_due_df)

    # --- Billing summary ---
    total_invoiced = (
        calculate_sum(df[INVOICE_COL]) if INVOICE_COL in df.columns else 0.0
    )
    avg_invoice = (
        calculate_average(df[INVOICE_COL]) if INVOICE_COL in df.columns else 0.0
    )
    billing_by_status: List[Dict] = []
    if BILLING_STATUS_COL in df.columns and INVOICE_COL in df.columns:
        billing_by_status = rank_by_sum(df, BILLING_STATUS_COL, INVOICE_COL)

    # --- Collection summary ---
    total_receivable = (
        calculate_sum(df[RECEIVABLE_COL]) if RECEIVABLE_COL in df.columns else 0.0
    )
    collection_by_status: List[Dict] = []
    if COLLECTION_STATUS_COL in df.columns and RECEIVABLE_COL in df.columns:
        collection_by_status = rank_by_sum(df, COLLECTION_STATUS_COL, RECEIVABLE_COL)

    # --- Pending receivables by customer ---
    receivables_by_customer: List[Dict] = []
    if RECEIVABLE_COL in df.columns and CUSTOMER_COL in df.columns:
        pending_df = df[df[RECEIVABLE_COL].apply(safe_numeric) > 0]
        if not pending_df.empty:
            cust_agg = (
                pending_df.groupby(CUSTOMER_COL)[RECEIVABLE_COL]
                .sum()
                .reset_index()
                .rename(columns={RECEIVABLE_COL: "total_receivable"})
                .sort_values("total_receivable", ascending=False)
            )
            receivables_by_customer = cust_agg.head(20).to_dict("records")

    return {
        # Execution
        "execution_by_status": exec_counts,
        "delayed_count": delayed_count,
        "past_due_count": past_due_count,
        "completed_count": completed_count,
        "open_count": open_count,
        "total_work_orders": len(df),
        "delayed_records": delayed_records[:30],  # cap for evidence payload
        # Billing
        "total_invoiced": total_invoiced,
        "average_invoice": avg_invoice,
        "billing_by_status": billing_by_status,
        "total_invoiced_fmt": format_currency(total_invoiced),
        # Collections
        "total_receivable": total_receivable,
        "collection_by_status": collection_by_status,
        "receivables_by_customer": receivables_by_customer,
        "total_receivable_fmt": format_currency(total_receivable),
    }


def _build_delayed_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    records = []
    for _, row in df.iterrows():
        records.append({
            "deal_name": row.get("deal_name", ""),
            "customer_code": row.get(CUSTOMER_COL, ""),
            "execution_status": row.get(EXEC_STATUS_COL, ""),
            "end_date": str(row[END_DATE_COL]) if pd.notna(row.get(END_DATE_COL)) else None,
            "sector": row.get(SECTOR_COL, ""),
        })
    return records


def _empty_workorder_kpis() -> Dict[str, Any]:
    return {
        "execution_by_status": {}, "delayed_count": 0, "past_due_count": 0,
        "completed_count": 0, "open_count": 0, "total_work_orders": 0,
        "delayed_records": [],
        "total_invoiced": 0.0, "average_invoice": 0.0, "billing_by_status": [],
        "total_invoiced_fmt": "₹0.00",
        "total_receivable": 0.0, "collection_by_status": [],
        "receivables_by_customer": [], "total_receivable_fmt": "₹0.00",
    }
