"""
Query understanding.

A deliberately lightweight, rule-based (keyword) intent + entity
extractor. This keeps the architecture simple (no extra LLM round-trip
just to classify intent) while still satisfying the requirement to
understand natural language questions and extract entities like
sector, customer, quarter, etc.

If the LLM later needs deeper nuance it still sees the raw question
alongside the computed analytics, so it can adapt phrasing --
but which analytics functions to RUN is decided here, deterministically.
"""

import calendar
import re
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

QUARTER_PATTERN = re.compile(r"\bq([1-4])\b", re.IGNORECASE)
MONTH_NAMES = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")
DATE_RANGE_PATTERN = re.compile(
    r"(?:from|between)\s+([\w\s]+?)\s+(?:to|and|till)\s+([\w\s]+)",
    re.IGNORECASE,
)
ROLLING_DAYS_PATTERN = re.compile(r"last\s+(\d+)\s+days?", re.IGNORECASE)
ROLLING_MONTHS_PATTERN = re.compile(r"last\s+(\d+)\s+months?", re.IGNORECASE)


@dataclass
class ParsedQuery:
    intents: List[str] = field(default_factory=list)
    sector: Optional[str] = None
    customer: Optional[str] = None
    quarter: Optional[int] = None
    month: Optional[int] = None
    year: Optional[int] = None
    only_open: Optional[bool] = None  # True=open only, False=all, None=unspecified
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    # --- Time-intelligence fields (used by evidence_builder) ---
    period: Optional[str] = None           # named period: "this_month", "last_quarter", etc.
    rolling_days: Optional[int] = None     # last N days
    rolling_months: Optional[int] = None   # last N months
    half: Optional[int] = None             # 1=Jan-Jun, 2=Jul-Dec
    start_date: Optional[date] = None      # custom range start
    end_date: Optional[date] = None        # custom range end
    # --- Trend flags ---
    trend_mom: bool = False
    trend_qoq: bool = False
    trend_yoy: bool = False
    trend_avg_monthly: bool = False
    trend_avg_quarterly: bool = False
    trend_avg_yearly: bool = False


# Keyword -> intent mapping. Order matters: first match wins per keyword group,
# but multiple intents can be detected in the same question.
INTENT_KEYWORDS = {
    "pipeline": ["pipeline", "open deals", "deal pipeline"],
    "revenue": ["revenue", "expected revenue", "income"],
    "sector_performance": ["sector performance", "best sector", "which sector", "by sector", "top sector", "sector breakdown", "sector"],
    "deals_by_stage": ["stage", "deal stage", "by stage"],
    "upcoming_closures": ["upcoming closure", "closing soon", "expected to close", "close date"],
    "delayed_work_orders": ["delayed", "delay", "overdue", "late work order"],
    "execution_summary": ["execution status", "execution summary", "work order status"],
    "billing_summary": ["billing", "invoice summary", "invoices"],
    "pending_receivables": ["receivable", "pending payment", "outstanding amount", "unpaid"],
    "collection_summary": ["collection", "collected", "collections"],
    "customer_lookup": ["customer", "client", "which customers", "account", "active deals and delayed", "cross-board", "cross board"],
    "leadership_update": ["leadership update", "leadership summary", "executive summary"],
    "time_intelligence": [
        "this month", "last month", "this quarter", "last quarter",
        "this year", "last year", "this week", "last week",
        "today", "yesterday", "last 7", "last 30", "last 90",
        "last 6 months", "last 12 months", "month over month",
        "quarter over quarter", "year over year", "mom", "qoq", "yoy",
        "trend", "by month", "by quarter", "by year",
        "first half", "second half", "h1", "h2",
        "between", "from", "january", "february", "march", "april",
        "may", "june", "july", "august", "september", "october",
        "november", "december",
    ],
}

SECTOR_HINT_PATTERN = re.compile(
    r"(?:in|for|within)\s+the\s+([a-zA-Z &]+?)\s+sector|(?:in|for)\s+([a-zA-Z &]+?)\s+sector",
    re.IGNORECASE,
)


def _detect_intents(text_lower: str) -> List[str]:
    detected = []
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            detected.append(intent)
    return detected


def _detect_quarter(text_lower: str) -> Optional[int]:
    match = QUARTER_PATTERN.search(text_lower)
    if match:
        return int(match.group(1))
    if "this quarter" in text_lower:
        current_month = date.today().month
        return (current_month - 1) // 3 + 1
    return None


def _detect_month(text_lower: str) -> Optional[int]:
    for name, idx in MONTH_NAMES.items():
        if name in text_lower:
            return idx
    return None


def _detect_year(text_lower: str) -> Optional[int]:
    match = YEAR_PATTERN.search(text_lower)
    return int(match.group(1)) if match else None


def _detect_sector(text: str) -> Optional[str]:
    match = SECTOR_HINT_PATTERN.search(text)
    if match:
        sector = match.group(1) or match.group(2)
        return sector.strip().title() if sector else None
    return None


def _detect_named_period(text_lower: str) -> Optional[str]:
    """Detect a named time period keyword."""
    if "today" in text_lower:
        return "today"
    if "yesterday" in text_lower:
        return "yesterday"
    if "last week" in text_lower:
        return "last_week"
    if "this week" in text_lower:
        return "this_week"
    if "last month" in text_lower:
        return "last_month"
    if "this month" in text_lower:
        return "this_month"
    if "last quarter" in text_lower:
        return "last_quarter"
    if "this quarter" in text_lower:
        return "this_quarter"
    if "last year" in text_lower:
        return "last_year"
    if "this year" in text_lower:
        return "this_year"
    return None


def _detect_rolling(text_lower: str):
    """Return (rolling_days, rolling_months) — at most one will be non-None."""
    m = ROLLING_DAYS_PATTERN.search(text_lower)
    if m:
        return int(m.group(1)), None
    m = ROLLING_MONTHS_PATTERN.search(text_lower)
    if m:
        return None, int(m.group(1))
    # Convenience aliases
    if "last 7 days" in text_lower:
        return 7, None
    if "last 30 days" in text_lower:
        return 30, None
    if "last 90 days" in text_lower:
        return 90, None
    if "last 6 months" in text_lower:
        return None, 6
    if "last 12 months" in text_lower:
        return None, 12
    return None, None


def _detect_half(text_lower: str) -> Optional[int]:
    if "first half" in text_lower or " h1 " in text_lower or text_lower.endswith(" h1"):
        return 1
    if "second half" in text_lower or " h2 " in text_lower or text_lower.endswith(" h2"):
        return 2
    # "jan" through "jun" with a year but no "jul"–"dec" → likely first-half
    return None


def _detect_trends(text_lower: str):
    """Return (mom, qoq, yoy, avg_monthly, avg_quarterly, avg_yearly)."""
    mom = any(kw in text_lower for kw in ["month over month", "mom", "month-over-month"])
    qoq = any(kw in text_lower for kw in ["quarter over quarter", "qoq", "quarter-over-quarter"])
    yoy = any(kw in text_lower for kw in ["year over year", "yoy", "year-over-year"])
    avg_m = "average deal" in text_lower and "month" in text_lower
    avg_q = "average deal" in text_lower and "quarter" in text_lower
    avg_y = "average deal" in text_lower and "year" in text_lower
    # "trend" without qualifier → default to MoM
    if "trend" in text_lower and not any([mom, qoq, yoy]):
        mom = True
    return mom, qoq, yoy, avg_m, avg_q, avg_y


def parse_query(message: str) -> ParsedQuery:
    """Parse a founder's natural-language question into structured intent."""
    text_lower = message.lower().strip()

    parsed = ParsedQuery()
    parsed.intents = _detect_intents(text_lower)
    parsed.sector = _detect_sector(message)
    parsed.quarter = _detect_quarter(text_lower)
    parsed.month = _detect_month(text_lower)
    parsed.year = _detect_year(text_lower)   # None unless user explicitly states a year

    if "open" in text_lower:
        parsed.only_open = True
    elif "all deals" in text_lower or "every deal" in text_lower:
        parsed.only_open = False

    # --- Time-intelligence extraction ---
    parsed.period = _detect_named_period(text_lower)
    parsed.rolling_days, parsed.rolling_months = _detect_rolling(text_lower)
    parsed.half = _detect_half(text_lower)
    (
        parsed.trend_mom,
        parsed.trend_qoq,
        parsed.trend_yoy,
        parsed.trend_avg_monthly,
        parsed.trend_avg_quarterly,
        parsed.trend_avg_yearly,
    ) = _detect_trends(text_lower)

    # If no clear intent was detected at all, default to a broad overview
    # rather than blocking the user with a clarification.
    if not parsed.intents:
        parsed.intents = ["pipeline", "revenue"]

    # Ambiguity check: bare "pipeline" question without qualifying whether
    # it means open deals only or everything.
    if (
        "pipeline" in parsed.intents
        and parsed.only_open is None
        and len(text_lower.split()) <= 4
    ):
        parsed.needs_clarification = True
        parsed.clarification_question = (
            "Do you want the pipeline value for all deals, or only open deals?"
        )

    return parsed
