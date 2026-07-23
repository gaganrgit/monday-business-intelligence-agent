"""
backend/helpers/time_intelligence_helper.py

All date-based filtering and trend analytics.

Rules:
  - All date arithmetic uses Python datetime / pandas ONLY.
  - No LLM ever performs date math.
  - Each public function accepts a DataFrame and a time spec, filters to the
    relevant window, then delegates computation to the domain helpers.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from backend.app.logger import get_logger
from backend.helpers.calculation_helper import (
    calculate_average,
    calculate_sum,
    format_currency,
    growth,
    safe_numeric,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALUE_COL = "deal_value"
INVOICE_COL = "invoice_amount"


def _effective_date_col(df: pd.DataFrame, preferred_cols: List[str]) -> Optional[str]:
    """Return the first column from preferred_cols that exists in df."""
    for col in preferred_cols:
        if col in df.columns:
            logger.info(f"Effective date column selected: '{col}' (evaluated candidates: {preferred_cols})")
            return col
    logger.warning(f"VALIDATION WARNING: No date column found in DataFrame out of candidates {preferred_cols}")
    return None


def _filter_by_date_range(
    df: pd.DataFrame,
    date_col: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Filter df so that date_col falls within [start, end] inclusive."""
    if df.empty or date_col not in df.columns:
        return df.iloc[0:0]
    col = df[date_col]
    mask = col.notna() & (col >= start) & (col <= end)
    return df[mask]


def _month_range(year: int, month: int) -> Tuple[date, date]:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _quarter_range(year: int, quarter: int) -> Tuple[date, date]:
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    last_day = calendar.monthrange(year, end_month)[1]
    return date(year, start_month, 1), date(year, end_month, last_day)


def _year_range(year: int) -> Tuple[date, date]:
    return date(year, 1, 1), date(year, 12, 31)


def _today() -> date:
    return date.today()


# ---------------------------------------------------------------------------
# Named periods
# ---------------------------------------------------------------------------


def filter_today(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    t = _today()
    return _filter_by_date_range(df, date_col, t, t)


def filter_yesterday(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    t = _today() - timedelta(days=1)
    return _filter_by_date_range(df, date_col, t, t)


def filter_this_week(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    t = _today()
    start = t - timedelta(days=t.weekday())  # Monday
    return _filter_by_date_range(df, date_col, start, t)


def filter_last_week(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    t = _today()
    this_monday = t - timedelta(days=t.weekday())
    last_monday = this_monday - timedelta(weeks=1)
    last_sunday = this_monday - timedelta(days=1)
    return _filter_by_date_range(df, date_col, last_monday, last_sunday)


def filter_this_month(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    t = _today()
    start, end = _month_range(t.year, t.month)
    return _filter_by_date_range(df, date_col, start, t)


def filter_last_month(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    t = _today()
    if t.month == 1:
        y, m = t.year - 1, 12
    else:
        y, m = t.year, t.month - 1
    start, end = _month_range(y, m)
    return _filter_by_date_range(df, date_col, start, end)


def filter_this_quarter(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    t = _today()
    q = (t.month - 1) // 3 + 1
    start, end = _quarter_range(t.year, q)
    return _filter_by_date_range(df, date_col, start, t)


def filter_last_quarter(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    t = _today()
    q = (t.month - 1) // 3 + 1
    if q == 1:
        prev_q, y = 4, t.year - 1
    else:
        prev_q, y = q - 1, t.year
    start, end = _quarter_range(y, prev_q)
    return _filter_by_date_range(df, date_col, start, end)


def filter_this_year(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    t = _today()
    start, end = _year_range(t.year)
    return _filter_by_date_range(df, date_col, start, t)


def filter_last_year(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    t = _today()
    start, end = _year_range(t.year - 1)
    return _filter_by_date_range(df, date_col, start, end)


# ---------------------------------------------------------------------------
# Rolling windows
# ---------------------------------------------------------------------------


def filter_last_n_days(df: pd.DataFrame, date_col: str, n: int) -> pd.DataFrame:
    t = _today()
    return _filter_by_date_range(df, date_col, t - timedelta(days=n), t)


def filter_last_n_months(df: pd.DataFrame, date_col: str, n: int) -> pd.DataFrame:
    t = _today()
    # Approximate: n * 30 days
    start = t - timedelta(days=n * 30)
    return _filter_by_date_range(df, date_col, start, t)


# ---------------------------------------------------------------------------
# Specific periods
# ---------------------------------------------------------------------------


def filter_by_month_year(df: pd.DataFrame, date_col: str, year: int, month: int) -> pd.DataFrame:
    start, end = _month_range(year, month)
    return _filter_by_date_range(df, date_col, start, end)


def filter_by_year(df: pd.DataFrame, date_col: str, year: int) -> pd.DataFrame:
    start, end = _year_range(year)
    return _filter_by_date_range(df, date_col, start, end)


def filter_by_quarter_year(df: pd.DataFrame, date_col: str, year: int, quarter: int) -> pd.DataFrame:
    start, end = _quarter_range(year, quarter)
    return _filter_by_date_range(df, date_col, start, end)


def filter_first_half(df: pd.DataFrame, date_col: str, year: int) -> pd.DataFrame:
    """January – June of a given year."""
    return _filter_by_date_range(df, date_col, date(year, 1, 1), date(year, 6, 30))


def filter_second_half(df: pd.DataFrame, date_col: str, year: int) -> pd.DataFrame:
    """July – December of a given year."""
    return _filter_by_date_range(df, date_col, date(year, 7, 1), date(year, 12, 31))


def filter_between_dates(
    df: pd.DataFrame,
    date_col: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    return _filter_by_date_range(df, date_col, start, end)


def filter_from_month_to_today(
    df: pd.DataFrame,
    date_col: str,
    year: int,
    month: int,
) -> pd.DataFrame:
    start = date(year, month, 1)
    return _filter_by_date_range(df, date_col, start, _today())


# ---------------------------------------------------------------------------
# Trend generators (MoM / QoQ / YoY)
# ---------------------------------------------------------------------------


def _sum_for_window(df: pd.DataFrame, date_col: str, value_col: str, start: date, end: date) -> float:
    filtered = _filter_by_date_range(df, date_col, start, end)
    if filtered.empty or value_col not in filtered.columns:
        return 0.0
    return calculate_sum(filtered[value_col])


def revenue_trend_mom(
    df: pd.DataFrame,
    date_col: str,
    value_col: str = VALUE_COL,
    months_back: int = 12,
) -> List[Dict[str, Any]]:
    """Month-over-month revenue trend for the last `months_back` months."""
    t = _today()
    results = []
    for i in range(months_back - 1, -1, -1):
        # Go back i months from current month
        total_months = t.month - 1 - i
        year = t.year + total_months // 12
        month = total_months % 12 + 1
        # Simpler: subtract months using calendar arithmetic
        year, month = _subtract_months(t.year, t.month, i)
        start, end = _month_range(year, month)
        rev = _sum_for_window(df, date_col, value_col, start, end)
        label = f"{calendar.month_abbr[month]} {year}"
        results.append({"period": label, "year": year, "month": month, "revenue": rev, "revenue_fmt": format_currency(rev)})

    # Attach growth vs previous period
    for i in range(1, len(results)):
        g = growth(results[i]["revenue"], results[i - 1]["revenue"])
        results[i]["growth_pct"] = g["percentage"]
        results[i]["growth_abs"] = g["difference"]
    if results:
        results[0]["growth_pct"] = None
        results[0]["growth_abs"] = None

    return results


def revenue_trend_qoq(
    df: pd.DataFrame,
    date_col: str,
    value_col: str = VALUE_COL,
    quarters_back: int = 8,
) -> List[Dict[str, Any]]:
    """Quarter-over-quarter revenue trend."""
    t = _today()
    current_q = (t.month - 1) // 3 + 1
    results = []

    for i in range(quarters_back - 1, -1, -1):
        year, q = _subtract_quarters(t.year, current_q, i)
        start, end = _quarter_range(year, q)
        rev = _sum_for_window(df, date_col, value_col, start, end)
        label = f"Q{q} {year}"
        results.append({"period": label, "year": year, "quarter": q, "revenue": rev, "revenue_fmt": format_currency(rev)})

    for i in range(1, len(results)):
        g = growth(results[i]["revenue"], results[i - 1]["revenue"])
        results[i]["growth_pct"] = g["percentage"]
        results[i]["growth_abs"] = g["difference"]
    if results:
        results[0]["growth_pct"] = None
        results[0]["growth_abs"] = None

    return results


def revenue_trend_yoy(
    df: pd.DataFrame,
    date_col: str,
    value_col: str = VALUE_COL,
    years_back: int = 5,
) -> List[Dict[str, Any]]:
    """Year-over-year revenue trend."""
    t = _today()
    results = []
    for i in range(years_back - 1, -1, -1):
        year = t.year - i
        start, end = _year_range(year)
        rev = _sum_for_window(df, date_col, value_col, start, end)
        results.append({"period": str(year), "year": year, "revenue": rev, "revenue_fmt": format_currency(rev)})

    for i in range(1, len(results)):
        g = growth(results[i]["revenue"], results[i - 1]["revenue"])
        results[i]["growth_pct"] = g["percentage"]
        results[i]["growth_abs"] = g["difference"]
    if results:
        results[0]["growth_pct"] = None
        results[0]["growth_abs"] = None

    return results


def avg_deal_value_by_month(
    df: pd.DataFrame,
    date_col: str,
    value_col: str = VALUE_COL,
    months_back: int = 12,
) -> List[Dict[str, Any]]:
    """Average deal value per month for the last `months_back` months."""
    t = _today()
    results = []
    for i in range(months_back - 1, -1, -1):
        year, month = _subtract_months(t.year, t.month, i)
        start, end = _month_range(year, month)
        filtered = _filter_by_date_range(df, date_col, start, end)
        avg = calculate_average(filtered[value_col]) if not filtered.empty and value_col in filtered.columns else 0.0
        label = f"{calendar.month_abbr[month]} {year}"
        results.append({"period": label, "year": year, "month": month, "avg_deal_value": avg, "avg_deal_fmt": format_currency(avg)})
    return results


def avg_deal_value_by_quarter(
    df: pd.DataFrame,
    date_col: str,
    value_col: str = VALUE_COL,
    quarters_back: int = 8,
) -> List[Dict[str, Any]]:
    t = _today()
    current_q = (t.month - 1) // 3 + 1
    results = []
    for i in range(quarters_back - 1, -1, -1):
        year, q = _subtract_quarters(t.year, current_q, i)
        start, end = _quarter_range(year, q)
        filtered = _filter_by_date_range(df, date_col, start, end)
        avg = calculate_average(filtered[value_col]) if not filtered.empty and value_col in filtered.columns else 0.0
        results.append({"period": f"Q{q} {year}", "year": year, "quarter": q, "avg_deal_value": avg, "avg_deal_fmt": format_currency(avg)})
    return results


def avg_deal_value_by_year(
    df: pd.DataFrame,
    date_col: str,
    value_col: str = VALUE_COL,
    years_back: int = 5,
) -> List[Dict[str, Any]]:
    t = _today()
    results = []
    for i in range(years_back - 1, -1, -1):
        year = t.year - i
        start, end = _year_range(year)
        filtered = _filter_by_date_range(df, date_col, start, end)
        avg = calculate_average(filtered[value_col]) if not filtered.empty and value_col in filtered.columns else 0.0
        results.append({"period": str(year), "year": year, "avg_deal_value": avg, "avg_deal_fmt": format_currency(avg)})
    return results


# ---------------------------------------------------------------------------
# High-level dispatcher — called by chat_orchestrator
# ---------------------------------------------------------------------------


def apply_time_filter(
    df: pd.DataFrame,
    date_col: str,
    *,
    period: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    quarter: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    rolling_days: Optional[int] = None,
    rolling_months: Optional[int] = None,
    half: Optional[int] = None,  # 1 = Jan-Jun, 2 = Jul-Dec
) -> pd.DataFrame:
    """
    Single entry-point for time filtering. Returns a filtered DataFrame.

    Priority order:
      1. Explicit date range (start_date / end_date)
      2. Rolling window (rolling_days / rolling_months)
      3. Named period string
      4. year + quarter → quarter filter
      5. year + month → month-year filter
      6. year + half → half-year filter
      7. year only → full-year filter
    """
    logger.info("=================== [TIME INTELLIGENCE] ===================")
    initial_rows = len(df)
    logger.info(f"Target Column: {date_col} | Initial Row Count: {initial_rows}")
    logger.info(
        f"Filter Input Parameters: period={period}, year={year}, month={month}, quarter={quarter}, "
        f"start_date={start_date}, end_date={end_date}, rolling_days={rolling_days}, "
        f"rolling_months={rolling_months}, half={half}"
    )

    if date_col not in df.columns:
        logger.warning(f"VALIDATION WARNING: Date column '{date_col}' is missing from DataFrame. Skipping time filter.")
        return df

    filtered_df = df
    reason = ""

    if start_date and end_date:
        reason = f"Explicit date range: {start_date} to {end_date}"
        filtered_df = filter_between_dates(df, date_col, start_date, end_date)
    elif rolling_days:
        reason = f"Rolling days window: last {rolling_days} days"
        filtered_df = filter_last_n_days(df, date_col, rolling_days)
    elif rolling_months:
        reason = f"Rolling months window: last {rolling_months} months"
        filtered_df = filter_last_n_months(df, date_col, rolling_months)
    else:
        named = (period or "").lower().strip()
        if named == "today":
            reason = "Named period: today"
            filtered_df = filter_today(df, date_col)
        elif named == "yesterday":
            reason = "Named period: yesterday"
            filtered_df = filter_yesterday(df, date_col)
        elif named in ("this_week", "this week"):
            reason = "Named period: this_week"
            filtered_df = filter_this_week(df, date_col)
        elif named in ("last_week", "last week"):
            reason = "Named period: last_week"
            filtered_df = filter_last_week(df, date_col)
        elif named in ("this_month", "this month"):
            reason = "Named period: this_month"
            filtered_df = filter_this_month(df, date_col)
        elif named in ("last_month", "last month"):
            reason = "Named period: last_month"
            filtered_df = filter_last_month(df, date_col)
        elif named in ("this_quarter", "this quarter"):
            reason = "Named period: this_quarter"
            filtered_df = filter_this_quarter(df, date_col)
        elif named in ("last_quarter", "last quarter"):
            reason = "Named period: last_quarter"
            filtered_df = filter_last_quarter(df, date_col)
        elif named in ("this_year", "this year"):
            reason = "Named period: this_year"
            filtered_df = filter_this_year(df, date_col)
        elif named in ("last_year", "last year"):
            reason = "Named period: last_year"
            filtered_df = filter_last_year(df, date_col)
        elif year and quarter:
            reason = f"Quarter-year filter: Q{quarter} {year}"
            filtered_df = filter_by_quarter_year(df, date_col, year, quarter)
        elif year and month:
            reason = f"Month-year filter: Month {month}, {year}"
            filtered_df = filter_by_month_year(df, date_col, year, month)
        elif year and half == 1:
            reason = f"First half filter: H1 {year}"
            filtered_df = filter_first_half(df, date_col, year)
        elif year and half == 2:
            reason = f"Second half filter: H2 {year}"
            filtered_df = filter_second_half(df, date_col, year)
        elif year:
            reason = f"Full year filter: {year}"
            filtered_df = filter_by_year(df, date_col, year)
        else:
            reason = "No time parameters specified — time filter skipped"
            filtered_df = df

    filtered_rows = len(filtered_df)
    logger.info(f"Filter Logic Applied: {reason}")
    logger.info(f"Time Filtering Output: {initial_rows} rows -> {filtered_rows} rows")

    if initial_rows > 0 and filtered_rows == 0 and reason != "No time parameters specified — time filter skipped":
        logger.warning(
            f"VALIDATION WARNING: Time filter resulted in 0 rows (empty time window) "
            f"for column '{date_col}' under filter '{reason}'."
        )

    return filtered_df


# ---------------------------------------------------------------------------
# Internal arithmetic helpers
# ---------------------------------------------------------------------------


def _subtract_months(year: int, month: int, n: int) -> Tuple[int, int]:
    """Subtract n months from (year, month)."""
    total = year * 12 + (month - 1) - n
    return total // 12, total % 12 + 1


def _subtract_quarters(year: int, quarter: int, n: int) -> Tuple[int, int]:
    """Subtract n quarters from (year, quarter)."""
    total = year * 4 + (quarter - 1) - n
    return total // 4, total % 4 + 1
