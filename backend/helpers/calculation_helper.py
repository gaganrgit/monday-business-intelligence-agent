"""
backend/helpers/calculation_helper.py

Core deterministic calculation utilities for the Business Intelligence Agent.
No LLM calls are made here. All functions operate on plain Python types or
pandas DataFrames and return JSON-serializable results.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Dict, Iterable, List

import pandas as pd


# ============================================================
# SAFE CONVERSION
# ============================================================


def safe_numeric(value: Any, default: float = 0.0) -> float:
    """Safely convert any value to float."""
    if value is None:
        return default

    if isinstance(value, (int, float)):
        if math.isnan(value):
            return default
        return float(value)

    if isinstance(value, str):
        value = (
            value.replace(",", "")
            .replace("₹", "")
            .replace("$", "")
            .strip()
        )
        if value == "":
            return default

    try:
        return float(value)
    except Exception:
        return default


def numeric_series(values: Iterable[Any]) -> List[float]:
    """Convert an iterable to a list of non-zero floats."""
    return [safe_numeric(v) for v in values if safe_numeric(v) != 0]


# ============================================================
# BASIC STATS
# ============================================================


def calculate_sum(values) -> float:
    return round(sum(numeric_series(values)), 2)


def calculate_count(values) -> int:
    return len(numeric_series(values))


def calculate_average(values) -> float:
    nums = numeric_series(values)
    if not nums:
        return 0
    return round(sum(nums) / len(nums), 2)


def calculate_min(values):
    nums = numeric_series(values)
    if not nums:
        return 0
    return min(nums)


def calculate_max(values):
    nums = numeric_series(values)
    if not nums:
        return 0
    return max(nums)


def calculate_median(values):
    nums = numeric_series(values)
    if not nums:
        return 0
    return round(statistics.median(nums), 2)


def calculate_std(values):
    nums = numeric_series(values)
    if len(nums) < 2:
        return 0
    return round(statistics.stdev(nums), 2)


# ============================================================
# SAFE MATH
# ============================================================


def safe_divide(a, b, default=0):
    a = safe_numeric(a)
    b = safe_numeric(b)
    if b == 0:
        return default
    return a / b


def calculate_percentage(part, total):
    return round(safe_divide(part * 100, total), 2)


def calculate_ratio(a, b):
    return round(safe_divide(a, b), 4)


def calculate_difference(current, previous):
    return round(safe_numeric(current) - safe_numeric(previous), 2)


def calculate_percentage_change(current, previous):
    current = safe_numeric(current)
    previous = safe_numeric(previous)
    if previous == 0:
        return 0
    return round(((current - previous) / previous) * 100, 2)


# ============================================================
# PIPELINE CALCULATIONS
# ============================================================


def total_pipeline(df: pd.DataFrame, value_column: str) -> float:
    return calculate_sum(df[value_column])


def average_deal_size(df: pd.DataFrame, value_column: str) -> float:
    return calculate_average(df[value_column])


def largest_deal(df: pd.DataFrame, value_column: str):
    if df.empty:
        return None
    idx = df[value_column].astype(float).idxmax()
    return df.loc[idx].to_dict()


def smallest_deal(df: pd.DataFrame, value_column: str):
    if df.empty:
        return None
    idx = df[value_column].astype(float).idxmin()
    return df.loc[idx].to_dict()


def weighted_pipeline(df: pd.DataFrame, value_column: str, probability_column: str) -> float:
    if df.empty:
        return 0
    values = df[value_column].apply(safe_numeric)
    probabilities = df[probability_column].apply(safe_numeric).fillna(0) / 100
    return round((values * probabilities).sum(), 2)


# ============================================================
# GROUPING
# ============================================================


def group_sum(df: pd.DataFrame, group_column: str, value_column: str) -> Dict[str, float]:
    if df.empty:
        return {}
    grouped = (
        df.groupby(group_column)[value_column]
        .sum()
        .sort_values(ascending=False)
    )
    return grouped.to_dict()


def group_count(df: pd.DataFrame, group_column: str) -> Dict[str, int]:
    if df.empty:
        return {}
    return df.groupby(group_column).size().sort_values(ascending=False).to_dict()


# ============================================================
# TOP / BOTTOM N
# ============================================================


def top_n(df: pd.DataFrame, value_column: str, n: int = 5) -> List[Dict]:
    if df.empty:
        return []
    return df.sort_values(value_column, ascending=False).head(n).to_dict("records")


def bottom_n(df: pd.DataFrame, value_column: str, n: int = 5) -> List[Dict]:
    if df.empty:
        return []
    return df.sort_values(value_column).head(n).to_dict("records")


# ============================================================
# DATE-INDEPENDENT TRENDS
# ============================================================


def growth(current, previous) -> Dict[str, float]:
    return {
        "difference": calculate_difference(current, previous),
        "percentage": calculate_percentage_change(current, previous),
    }


# ============================================================
# RANKING
# ============================================================


def rank_by_sum(df: pd.DataFrame, group_column: str, value_column: str) -> List[Dict]:
    grouped = (
        df.groupby(group_column)[value_column]
        .sum()
        .sort_values(ascending=False)
    )
    return grouped.reset_index().to_dict("records")


# ============================================================
# FORMATTING
# ============================================================


def format_currency(value) -> str:
    value = safe_numeric(value)
    if value >= 1_000_000_000:
        return f"₹{value/1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"₹{value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"₹{value/1_000:.2f}K"
    return f"₹{value:.2f}"


def format_percentage(value) -> str:
    return f"{safe_numeric(value):.2f}%"
