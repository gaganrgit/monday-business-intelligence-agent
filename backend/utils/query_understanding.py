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


# Keyword -> intent mapping. Order matters: first match wins per keyword group,
# but multiple intents can be detected in the same question.
INTENT_KEYWORDS = {
    "pipeline": ["pipeline", "open deals", "deal pipeline"],
    "revenue": ["revenue", "expected revenue", "income"],
    "sector_performance": ["sector performance", "best sector", "which sector", "by sector"],
    "deals_by_stage": ["stage", "deal stage", "by stage"],
    "upcoming_closures": ["upcoming closure", "closing soon", "expected to close", "close date"],
    "delayed_work_orders": ["delayed", "delay", "overdue", "late work order"],
    "execution_summary": ["execution status", "execution summary", "work order status"],
    "billing_summary": ["billing", "invoice summary", "invoices"],
    "pending_receivables": ["receivable", "pending payment", "outstanding amount", "unpaid"],
    "collection_summary": ["collection", "collected", "collections"],
    "customer_lookup": ["customer", "client", "which customers", "account"],
    "leadership_update": ["leadership update", "leadership summary", "executive summary"],
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
    if "this quarter" in text_lower or "quarter" in text_lower:
        current_month = date.today().month
        return (current_month - 1) // 3 + 1
    return None


def _detect_month(text_lower: str) -> Optional[int]:
    for name, idx in MONTH_NAMES.items():
        if name in text_lower:
            return idx
    return None


def _detect_sector(text: str) -> Optional[str]:
    match = SECTOR_HINT_PATTERN.search(text)
    if match:
        sector = match.group(1) or match.group(2)
        return sector.strip().title() if sector else None
    return None


def parse_query(message: str) -> ParsedQuery:
    """Parse a founder's natural-language question into structured intent."""
    text_lower = message.lower().strip()

    parsed = ParsedQuery()
    parsed.intents = _detect_intents(text_lower)
    parsed.sector = _detect_sector(message)
    parsed.quarter = _detect_quarter(text_lower)
    parsed.month = _detect_month(text_lower)
    parsed.year = date.today().year

    if "open" in text_lower:
        parsed.only_open = True
    elif "all deals" in text_lower or "every deal" in text_lower:
        parsed.only_open = False

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
