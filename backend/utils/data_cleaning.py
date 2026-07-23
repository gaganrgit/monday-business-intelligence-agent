"""
Data cleaning utilities.

Converts raw monday.com items (list of dicts with a "columns" map keyed
by column title) into clean pandas DataFrames with normalized,
predictable field names, consistent casing, parsed dates, and safe
numeric conversions. Never raises on a single bad record -- bad
records are skipped and counted so the caller can surface a
data-quality note to the user.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd
from dateutil import parser as date_parser

from backend.app.logger import get_logger
from backend.models.data_models import (
    DEALS_FIELD_ALIASES,
    WORKORDERS_FIELD_ALIASES,
    DEALS_DATE_FIELDS,
    WORKORDERS_DATE_FIELDS,
    DEALS_NUMERIC_FIELDS,
    WORKORDERS_NUMERIC_FIELDS,
)

logger = get_logger(__name__)


# ----------------------------------------------------------------------
# Generic helpers
# ----------------------------------------------------------------------

def _normalize_header(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _build_alias_lookup(field_aliases: Dict[str, List[str]]) -> Dict[str, str]:
    """Flatten {canonical: [aliases]} into {alias_text: canonical}."""
    lookup: Dict[str, str] = {}
    for canonical, aliases in field_aliases.items():
        for alias in aliases:
            lookup[_normalize_header(alias)] = canonical
    return lookup


def _map_columns_to_canonical(
    columns: Dict[str, Any], alias_lookup: Dict[str, str]
) -> Dict[str, Any]:
    mapped: Dict[str, Any] = {}
    for raw_title, value in columns.items():
        canonical = alias_lookup.get(_normalize_header(raw_title))
        if canonical:
            mapped[canonical] = value
    return mapped


def normalize_text(value: Any) -> str:
    """Normalize free-text values: trim, collapse whitespace, title-case.

    Handles the classic 'Energy' / 'energy' / 'ENERGY' -> 'Energy' case.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if text == "" or text.lower() in ("null", "none", "n/a", "na"):
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.title()


def safe_float(value: Any) -> float:
    """Convert a value to float, stripping currency symbols/commas.

    Returns 0.0 (never raises) for anything that can't be parsed.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == "":
        return 0.0
    text = re.sub(r"[^\d.\-]", "", text)
    if text in ("", "-", ".", "-."):
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def safe_date(value: Any):
    """Parse a date string in (almost) any common format.

    Returns None (never raises) when the value is missing or invalid.
    """
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in ("null", "none", "n/a", "na"):
        return None
    try:
        return date_parser.parse(text, dayfirst=False, fuzzy=True).date()
    except (ValueError, OverflowError, TypeError):
        return None


# ----------------------------------------------------------------------
# Board-specific cleaning
# ----------------------------------------------------------------------

def clean_deals(raw_items: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Clean raw Deals board items into a normalized DataFrame.

    Returns (dataframe, quality_report).
    """
    logger.info("Cleaning Started")
    alias_lookup = _build_alias_lookup(DEALS_FIELD_ALIASES)

    rows = []
    missing_values_count = 0
    invalid_dates_count = 0
    skipped_records = 0

    for item in raw_items:
        try:
            mapped = _map_columns_to_canonical(item.get("columns", {}), alias_lookup)

            row = {
                "deal_name": mapped.get("deal_name") or item.get("name") or "Unnamed Deal",
                "owner_code": normalize_text(mapped.get("owner_code")),
                "client_code": normalize_text(mapped.get("client_code")),
                "deal_status": normalize_text(mapped.get("deal_status")),
                "deal_stage": normalize_text(mapped.get("deal_stage")),
                "product": normalize_text(mapped.get("product")),
                "sector": normalize_text(mapped.get("sector")) or "Unspecified",
            }

            for field in DEALS_NUMERIC_FIELDS:
                raw_val = mapped.get(field)
                if raw_val in (None, ""):
                    missing_values_count += 1
                row[field] = safe_float(raw_val)

            for field in DEALS_DATE_FIELDS:
                raw_val = mapped.get(field)
                parsed = safe_date(raw_val)
                if raw_val not in (None, "") and parsed is None:
                    invalid_dates_count += 1
                row[field] = parsed

            rows.append(row)
        except Exception as exc:  # never let one bad record crash the app
            skipped_records += 1
            logger.warning(f"Skipped malformed Deals record: {exc}")

    df = pd.DataFrame(rows)
    logger.info("Dates Normalized")

    quality_report = {
        "total_records": len(raw_items),
        "clean_records": len(df),
        "skipped_records": skipped_records,
        "missing_values": missing_values_count,
        "invalid_dates": invalid_dates_count,
    }
    if missing_values_count or invalid_dates_count or skipped_records:
        logger.warning(
            f"Missing Values Found: {missing_values_count} | "
            f"Invalid Dates: {invalid_dates_count} | Skipped: {skipped_records}"
        )
    logger.info("Cleaning Finished")
    return df, quality_report


def clean_work_orders(raw_items: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Clean raw Work Orders board items into a normalized DataFrame."""
    logger.info("Cleaning Started")
    alias_lookup = _build_alias_lookup(WORKORDERS_FIELD_ALIASES)

    rows = []
    missing_values_count = 0
    invalid_dates_count = 0
    skipped_records = 0

    for item in raw_items:
        try:
            mapped = _map_columns_to_canonical(item.get("columns", {}), alias_lookup)

            row = {
                "deal_name": mapped.get("deal_name") or item.get("name") or "Unnamed Work Order",
                "customer_code": normalize_text(mapped.get("customer_code")),
                "nature_of_work": normalize_text(mapped.get("nature_of_work")),
                "execution_status": normalize_text(mapped.get("execution_status")),
                "sector": normalize_text(mapped.get("sector")) or "Unspecified",
                "work_type": normalize_text(mapped.get("work_type")),
                "billing_status": normalize_text(mapped.get("billing_status")),
                "collection_status": normalize_text(mapped.get("collection_status")),
                "invoice_status": normalize_text(mapped.get("invoice_status")),
            }

            for field in WORKORDERS_NUMERIC_FIELDS:
                raw_val = mapped.get(field)
                if raw_val in (None, ""):
                    missing_values_count += 1
                row[field] = safe_float(raw_val)

            for field in WORKORDERS_DATE_FIELDS:
                raw_val = mapped.get(field)
                parsed = safe_date(raw_val)
                if raw_val not in (None, "") and parsed is None:
                    invalid_dates_count += 1
                row[field] = parsed

            rows.append(row)
        except Exception as exc:
            skipped_records += 1
            logger.warning(f"Skipped malformed Work Order record: {exc}")

    df = pd.DataFrame(rows)
    logger.info("Dates Normalized")

    quality_report = {
        "total_records": len(raw_items),
        "clean_records": len(df),
        "skipped_records": skipped_records,
        "missing_values": missing_values_count,
        "invalid_dates": invalid_dates_count,
    }
    if missing_values_count or invalid_dates_count or skipped_records:
        logger.warning(
            f"Missing Values Found: {missing_values_count} | "
            f"Invalid Dates: {invalid_dates_count} | Skipped: {skipped_records}"
        )
    logger.info("Cleaning Finished")
    return df, quality_report
