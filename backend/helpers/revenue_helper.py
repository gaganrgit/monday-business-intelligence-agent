"""
backend/helpers/revenue_helper.py

Deterministic revenue KPI computation from the cleaned Deals DataFrame.
No LLM calls. All arithmetic is Python / pandas.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from backend.helpers.calculation_helper import (
    calculate_average,
    calculate_count,
    calculate_max,
    calculate_min,
    calculate_median,
    calculate_std,
    calculate_sum,
    format_currency,
    group_sum,
    rank_by_sum,
    safe_numeric,
    top_n,
    bottom_n,
)

VALUE_COL = "deal_value"
SECTOR_COL = "sector"
CLIENT_COL = "client_code"
OWNER_COL = "owner_code"


def compute_revenue_kpis(df: pd.DataFrame) -> Dict[str, Any]:
    """Return a complete revenue KPI dict from the cleaned deals DataFrame."""
    if df.empty or VALUE_COL not in df.columns:
        return _empty_revenue_kpis()

    values = df[VALUE_COL].apply(safe_numeric)

    total_revenue = calculate_sum(values)
    average_revenue = calculate_average(values)
    largest_revenue = calculate_max(values)
    smallest_revenue = calculate_min(values)
    median_revenue = calculate_median(values)
    std_revenue = calculate_std(values)
    deal_count = calculate_count(values)

    # By sector
    by_sector: List[Dict] = []
    if SECTOR_COL in df.columns:
        by_sector = rank_by_sum(df, SECTOR_COL, VALUE_COL)

    # By client
    by_client: List[Dict] = []
    if CLIENT_COL in df.columns:
        by_client = rank_by_sum(df, CLIENT_COL, VALUE_COL)

    # By owner
    by_owner: List[Dict] = []
    if OWNER_COL in df.columns:
        by_owner = rank_by_sum(df, OWNER_COL, VALUE_COL)

    # Top / bottom customers
    top_customers: List[Dict] = []
    bottom_customers: List[Dict] = []
    if CLIENT_COL in df.columns:
        client_agg = (
            df.groupby(CLIENT_COL)[VALUE_COL]
            .sum()
            .reset_index()
            .rename(columns={VALUE_COL: "total_revenue"})
        )
        top_customers = top_n(client_agg, "total_revenue", n=5)
        bottom_customers = bottom_n(client_agg, "total_revenue", n=5)

    # Revenue distribution (quartiles)
    distribution = _revenue_distribution(values)

    return {
        "total_revenue": total_revenue,
        "average_revenue": average_revenue,
        "largest_revenue": largest_revenue,
        "smallest_revenue": smallest_revenue,
        "median_revenue": median_revenue,
        "std_revenue": std_revenue,
        "deal_count": deal_count,
        "revenue_by_sector": by_sector,
        "revenue_by_client": by_client,
        "revenue_by_owner": by_owner,
        "top_customers": top_customers,
        "bottom_customers": bottom_customers,
        "distribution": distribution,
        # Formatted
        "total_revenue_fmt": format_currency(total_revenue),
        "average_revenue_fmt": format_currency(average_revenue),
        "largest_revenue_fmt": format_currency(largest_revenue),
    }


def _revenue_distribution(values: pd.Series) -> Dict[str, float]:
    """Return quartile-based distribution of revenue values."""
    if values.empty:
        return {"q1": 0.0, "q2_median": 0.0, "q3": 0.0, "iqr": 0.0}
    q1 = float(round(values.quantile(0.25), 2))
    q2 = float(round(values.quantile(0.50), 2))
    q3 = float(round(values.quantile(0.75), 2))
    return {"q1": q1, "q2_median": q2, "q3": q3, "iqr": round(q3 - q1, 2)}


def _empty_revenue_kpis() -> Dict[str, Any]:
    return {
        "total_revenue": 0.0, "average_revenue": 0.0, "largest_revenue": 0.0,
        "smallest_revenue": 0.0, "median_revenue": 0.0, "std_revenue": 0.0,
        "deal_count": 0, "revenue_by_sector": [], "revenue_by_client": [],
        "revenue_by_owner": [], "top_customers": [], "bottom_customers": [],
        "distribution": {"q1": 0.0, "q2_median": 0.0, "q3": 0.0, "iqr": 0.0},
        "total_revenue_fmt": "₹0.00", "average_revenue_fmt": "₹0.00",
        "largest_revenue_fmt": "₹0.00",
    }
