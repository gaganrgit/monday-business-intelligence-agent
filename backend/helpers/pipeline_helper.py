"""
backend/helpers/pipeline_helper.py

Deterministic pipeline KPI computation.
All metrics are computed in pure Python / pandas — no LLM calls.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import pandas as pd

from backend.helpers.calculation_helper import (
    calculate_average,
    calculate_count,
    calculate_max,
    calculate_min,
    calculate_percentage,
    calculate_ratio,
    calculate_sum,
    format_currency,
    format_percentage,
    group_count,
    group_sum,
    largest_deal,
    rank_by_sum,
    safe_numeric,
    smallest_deal,
    top_n,
    weighted_pipeline,
)

# ---------------------------------------------------------------------------
# Closed-deal statuses (mirrors analytics_engine.py so no duplicate config)
# ---------------------------------------------------------------------------
_env_closed = os.getenv("CLOSED_DEAL_STATUSES", "")
if _env_closed.strip():
    CLOSED_STATUSES: set = {s.strip().title() for s in _env_closed.split(",") if s.strip()}
else:
    CLOSED_STATUSES = {
        "Won", "Closed Won", "Closed", "Lost", "Closed Lost",
        "Dead", "Rejected", "Cancelled", "Canceled",
    }

WON_STATUSES = {"Won", "Closed Won"}
LOST_STATUSES = {"Lost", "Closed Lost", "Dead", "Rejected", "Cancelled", "Canceled"}
ON_HOLD_STATUSES = {"On Hold", "Paused", "Pending"}

VALUE_COL = "deal_value"
PROB_COL = "closure_probability"
STATUS_COL = "deal_status"
OWNER_COL = "owner_code"


def _open_df(df: pd.DataFrame) -> pd.DataFrame:
    """Return only open (non-closed) deals."""
    if STATUS_COL not in df.columns:
        return df
    return df[~df[STATUS_COL].isin(CLOSED_STATUSES)]


def _status_df(df: pd.DataFrame, status_set: set) -> pd.DataFrame:
    if STATUS_COL not in df.columns:
        return df.iloc[0:0]
    return df[df[STATUS_COL].isin(status_set)]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_pipeline_kpis(df: pd.DataFrame) -> Dict[str, Any]:
    """Return a complete pipeline KPI dict from the cleaned deals DataFrame."""
    if df.empty:
        return _empty_pipeline_kpis()

    open_df = _open_df(df)
    won_df = _status_df(df, WON_STATUSES)
    lost_df = _status_df(df, LOST_STATUSES)
    on_hold_df = _status_df(df, ON_HOLD_STATUSES)

    total_count = len(df)
    open_count = len(open_df)
    won_count = len(won_df)
    lost_count = len(lost_df)
    on_hold_count = len(on_hold_df)

    total_value = calculate_sum(df[VALUE_COL]) if VALUE_COL in df.columns else 0.0
    open_value = calculate_sum(open_df[VALUE_COL]) if VALUE_COL in open_df.columns else 0.0
    won_value = calculate_sum(won_df[VALUE_COL]) if VALUE_COL in won_df.columns else 0.0
    lost_value = calculate_sum(lost_df[VALUE_COL]) if VALUE_COL in lost_df.columns else 0.0

    avg_deal = calculate_average(df[VALUE_COL]) if VALUE_COL in df.columns else 0.0
    avg_open = calculate_average(open_df[VALUE_COL]) if VALUE_COL in open_df.columns else 0.0

    wp = (
        weighted_pipeline(open_df, VALUE_COL, PROB_COL)
        if VALUE_COL in open_df.columns and PROB_COL in open_df.columns
        else 0.0
    )

    # Ratios (based on total deal count to avoid zero-division)
    open_ratio = calculate_percentage(open_count, total_count)
    win_ratio = calculate_percentage(won_count, total_count)
    loss_ratio = calculate_percentage(lost_count, total_count)

    # Pipeline by owner
    by_owner: List[Dict] = []
    if OWNER_COL in open_df.columns and VALUE_COL in open_df.columns:
        by_owner = rank_by_sum(open_df, OWNER_COL, VALUE_COL)

    # Pipeline by status
    by_status: Dict[str, float] = {}
    if STATUS_COL in df.columns and VALUE_COL in df.columns:
        by_status = group_sum(df, STATUS_COL, VALUE_COL)

    # Pipeline by probability bucket
    prob_buckets = _pipeline_by_probability(open_df)

    # Largest / smallest
    big = largest_deal(open_df, VALUE_COL) if VALUE_COL in open_df.columns else None
    small = smallest_deal(open_df, VALUE_COL) if VALUE_COL in open_df.columns else None

    return {
        # Counts
        "total_deal_count": total_count,
        "open_deal_count": open_count,
        "won_deal_count": won_count,
        "lost_deal_count": lost_count,
        "on_hold_count": on_hold_count,
        # Values
        "total_pipeline": total_value,
        "open_pipeline": open_value,
        "won_value": won_value,
        "lost_value": lost_value,
        "weighted_pipeline": wp,
        # Averages
        "average_deal_size": avg_deal,
        "average_open_deal_size": avg_open,
        # Extremes
        "largest_open_deal": _safe_deal_record(big),
        "smallest_open_deal": _safe_deal_record(small),
        # Ratios
        "open_ratio_pct": open_ratio,
        "win_ratio_pct": win_ratio,
        "loss_ratio_pct": loss_ratio,
        # Breakdowns
        "pipeline_by_owner": by_owner,
        "pipeline_by_status": by_status,
        "pipeline_by_probability": prob_buckets,
        # Formatted
        "open_pipeline_fmt": format_currency(open_value),
        "weighted_pipeline_fmt": format_currency(wp),
        "win_ratio_fmt": format_percentage(win_ratio),
    }


def _pipeline_by_probability(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Bucket open pipeline into 0-25 / 26-50 / 51-75 / 76-100 probability ranges."""
    if df.empty or PROB_COL not in df.columns or VALUE_COL not in df.columns:
        return []

    bins = [0, 25, 50, 75, 100]
    labels = ["0-25%", "26-50%", "51-75%", "76-100%"]
    tmp = df.copy()
    tmp["_bucket"] = pd.cut(
        tmp[PROB_COL].apply(safe_numeric).clip(0, 100),
        bins=bins,
        labels=labels,
        include_lowest=True,
    )
    grouped = (
        tmp.groupby("_bucket", observed=True)[VALUE_COL]
        .agg(total_value="sum", deal_count="count")
        .reset_index()
        .rename(columns={"_bucket": "probability_range"})
    )
    grouped["total_value"] = grouped["total_value"].round(2)
    return grouped.to_dict("records")


def _safe_deal_record(record) -> Dict[str, Any]:
    if record is None:
        return {}
    # Keep only JSON-serializable fields; convert dates to strings
    cleaned = {}
    for k, v in record.items():
        if hasattr(v, "isoformat"):
            cleaned[k] = v.isoformat()
        else:
            cleaned[k] = v
    return cleaned


def _empty_pipeline_kpis() -> Dict[str, Any]:
    return {
        "total_deal_count": 0, "open_deal_count": 0, "won_deal_count": 0,
        "lost_deal_count": 0, "on_hold_count": 0,
        "total_pipeline": 0.0, "open_pipeline": 0.0, "won_value": 0.0,
        "lost_value": 0.0, "weighted_pipeline": 0.0,
        "average_deal_size": 0.0, "average_open_deal_size": 0.0,
        "largest_open_deal": {}, "smallest_open_deal": {},
        "open_ratio_pct": 0.0, "win_ratio_pct": 0.0, "loss_ratio_pct": 0.0,
        "pipeline_by_owner": [], "pipeline_by_status": {}, "pipeline_by_probability": [],
        "open_pipeline_fmt": "₹0.00", "weighted_pipeline_fmt": "₹0.00", "win_ratio_fmt": "0.00%",
    }
