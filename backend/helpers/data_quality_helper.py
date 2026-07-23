"""
backend/helpers/data_quality_helper.py

Deterministic data-completeness and integrity checks.
Returns counts only — no LLM involvement.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from backend.helpers.calculation_helper import safe_numeric


def compute_deals_quality(df: pd.DataFrame) -> Dict[str, Any]:
    """Return data-quality metrics for the cleaned deals DataFrame."""
    if df.empty:
        return _empty_quality("deals")

    total = len(df)

    # Missing key fields
    missing_sector = _missing_count(df, "sector")
    missing_probability = _missing_count(df, "closure_probability")
    missing_client = _missing_count(df, "client_code")
    missing_owner = _missing_count(df, "owner_code")
    missing_deal_value = _missing_count(df, "deal_value")

    # Missing / invalid dates
    missing_close_date = _missing_date_count(df, "close_date")
    missing_tentative_close = _missing_date_count(df, "tentative_close_date")
    missing_created_date = _missing_date_count(df, "created_date")

    # Invalid amounts (negative deal values)
    invalid_amounts = 0
    if "deal_value" in df.columns:
        invalid_amounts = int((df["deal_value"].apply(safe_numeric) < 0).sum())

    # Duplicates
    duplicate_deals = _duplicate_count(df, "deal_name")
    duplicate_clients = _duplicate_count(df, "client_code")
    duplicate_deals_list = _duplicate_list(df, "deal_name")
    duplicate_clients_list = _duplicate_list(df, "client_code")

    # Zero-value deals
    zero_value_deals = 0
    if "deal_value" in df.columns:
        zero_value_deals = int((df["deal_value"].apply(safe_numeric) == 0).sum())

    warnings: List[str] = []
    if missing_sector > 0:
        warnings.append(f"{missing_sector} deals missing sector.")
    if missing_probability > 0:
        warnings.append(f"{missing_probability} deals missing closure probability.")
    if missing_client > 0:
        warnings.append(f"{missing_client} deals missing client code.")
    if invalid_amounts > 0:
        warnings.append(f"{invalid_amounts} deals with negative deal value.")
    if zero_value_deals > 0:
        warnings.append(f"{zero_value_deals} deals with zero deal value.")
    if duplicate_deals > 0:
        names_str = ", ".join([f"{item['value']} ({item['count']}x)" for item in duplicate_deals_list[:5]])
        warnings.append(f"{duplicate_deals} duplicate deal names detected ({names_str}).")
    if duplicate_clients > 0:
        clients_str = ", ".join([f"{item['value']} ({item['count']}x)" for item in duplicate_clients_list[:5]])
        warnings.append(f"{duplicate_clients} duplicate client codes detected ({clients_str}).")

    return {
        "board": "deals",
        "total_records": total,
        "missing_sector": missing_sector,
        "missing_probability": missing_probability,
        "missing_client": missing_client,
        "missing_owner": missing_owner,
        "missing_deal_value": missing_deal_value,
        "missing_close_date": missing_close_date,
        "missing_tentative_close_date": missing_tentative_close,
        "missing_created_date": missing_created_date,
        "invalid_amounts": invalid_amounts,
        "zero_value_deals": zero_value_deals,
        "duplicate_deals": duplicate_deals,
        "duplicate_clients": duplicate_clients,
        "duplicate_deals_list": duplicate_deals_list,
        "duplicate_clients_list": duplicate_clients_list,
        "warnings": warnings,
    }


def compute_workorders_quality(df: pd.DataFrame) -> Dict[str, Any]:
    """Return data-quality metrics for the cleaned work-orders DataFrame."""
    if df.empty:
        return _empty_quality("work_orders")

    total = len(df)

    missing_customer = _missing_count(df, "customer_code")
    missing_sector = _missing_count(df, "sector")
    missing_invoice = _missing_count(df, "invoice_amount")
    missing_receivable = _missing_count(df, "amount_receivable")

    missing_start_date = _missing_date_count(df, "start_date")
    missing_end_date = _missing_date_count(df, "end_date")

    invalid_amounts = 0
    if "invoice_amount" in df.columns:
        invalid_amounts = int((df["invoice_amount"].apply(safe_numeric) < 0).sum())

    duplicate_work_orders = _duplicate_count(df, "deal_name")
    duplicate_customers = _duplicate_count(df, "customer_code")
    duplicate_work_orders_list = _duplicate_list(df, "deal_name")
    duplicate_customers_list = _duplicate_list(df, "customer_code")

    warnings: List[str] = []
    if missing_customer > 0:
        warnings.append(f"{missing_customer} work orders missing customer code.")
    if missing_invoice > 0:
        warnings.append(f"{missing_invoice} work orders missing invoice amount.")
    if invalid_amounts > 0:
        warnings.append(f"{invalid_amounts} work orders with negative invoice amount.")
    if duplicate_work_orders > 0:
        names_str = ", ".join([f"{item['value']} ({item['count']}x)" for item in duplicate_work_orders_list[:5]])
        warnings.append(f"{duplicate_work_orders} duplicate work order names detected ({names_str}).")
    if duplicate_customers > 0:
        cust_str = ", ".join([f"{item['value']} ({item['count']}x)" for item in duplicate_customers_list[:5]])
        warnings.append(f"{duplicate_customers} duplicate customer codes detected ({cust_str}).")

    return {
        "board": "work_orders",
        "total_records": total,
        "missing_customer": missing_customer,
        "missing_sector": missing_sector,
        "missing_invoice": missing_invoice,
        "missing_receivable": missing_receivable,
        "missing_start_date": missing_start_date,
        "missing_end_date": missing_end_date,
        "invalid_amounts": invalid_amounts,
        "duplicate_work_orders": duplicate_work_orders,
        "duplicate_customers": duplicate_customers,
        "duplicate_work_orders_list": duplicate_work_orders_list,
        "duplicate_customers_list": duplicate_customers_list,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _missing_count(df: pd.DataFrame, col: str) -> int:
    if col not in df.columns:
        return 0
    return int(df[col].isnull().sum()) + int((df[col].astype(str).str.strip() == "").sum())


def _missing_date_count(df: pd.DataFrame, col: str) -> int:
    if col not in df.columns:
        return 0
    return int(df[col].isnull().sum())


def _duplicate_count(df: pd.DataFrame, col: str) -> int:
    if col not in df.columns:
        return 0
    # Count records that share a name/code with at least one other record
    vc = df[col].dropna().value_counts()
    return int((vc > 1).sum())


def _duplicate_list(df: pd.DataFrame, col: str, max_items: int = 10) -> List[Dict[str, Any]]:
    if col not in df.columns:
        return []
    series = df[col].dropna().astype(str).str.strip()
    series = series[series != ""]
    vc = series.value_counts()
    dups = vc[vc > 1]
    result = []
    for val, count in dups.head(max_items).items():
        result.append({"value": str(val), "count": int(count)})
    return result


def _empty_quality(board: str) -> Dict[str, Any]:
    return {"board": board, "total_records": 0, "warnings": []}
