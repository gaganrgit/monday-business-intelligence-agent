"""
Lightweight field definitions for the two monday.com boards.

These are simple constants/type hints, not ORM models -- the app has
no database. They exist so that column-name matching (which can vary
slightly between how a user names their monday.com columns) is
centralized in one place instead of scattered across the codebase.
"""

from typing import List

# Deals board -- canonical field name -> list of acceptable aliases
# found in monday.com column titles (case-insensitive match).
DEALS_FIELD_ALIASES = {
    "deal_name": ["deal name", "name", "deal"],
    "owner_code": ["owner code", "owner", "deal owner"],
    "client_code": ["client code", "client", "customer code", "customer", "customer name code"],
    "deal_status": ["deal status", "status"],
    "deal_stage": ["deal stage", "stage"],
    "deal_value": ["masked deal value", "deal value", "value", "amount", "deal amount", "contract value", "deal size", "opportunity value"],
    "closure_probability": ["closure probability", "probability", "close probability"],
    "close_date": ["close date (a)", "close date", "closed date"],
    "tentative_close_date": ["tentative close date", "expected close date", "tentative close"],
    "product": ["product deal", "product"],
    "sector": ["sector/service", "sector", "industry", "service/sector"],
    "created_date": ["created date", "created at", "creation date"],
}

# Work Orders board -- canonical field name -> aliases
WORKORDERS_FIELD_ALIASES = {
    "deal_name": ["deal name", "name", "deal"],
    "customer_code": ["customer name code", "customer code", "customer", "client code", "client", "customer name"],
    "nature_of_work": ["nature of work", "work nature", "type of work"],
    "execution_status": ["execution status", "status"],
    "start_date": ["probable start date", "start date", "planned start date"],
    "end_date": ["probable end date", "end date", "planned end date", "due date"],
    "data_delivery_date": ["data delivery date", "delivery date"],
    "po_date": ["date of po/loi", "po date", "purchase order date"],
    "sector": ["sector", "industry", "sector/service"],
    "work_type": ["type of work", "work type"],
    "invoice_amount": ["amount in rupees (incl of gst) (masked)", "billed value in rupees (incl of gst.) (masked)", "amount in rupees (excl of gst) (masked)", "billed value in rupees (excl of gst.) (masked)", "invoice amount", "invoice value", "billed value"],
    "amount_receivable": ["amount receivable (masked)", "amount receivable", "receivable amount", "receivable"],
    "billing_status": ["billing status", "wo status (billed)"],
    "collection_status": ["collection status", "actual collection month"],
    "quantity": ["quantity by ops", "quantities as per po", "quantity billed (till date)", "quantity", "qty"],
    "invoice_status": ["invoice status"],
}

DEALS_DATE_FIELDS: List[str] = ["close_date", "tentative_close_date", "created_date"]
WORKORDERS_DATE_FIELDS: List[str] = ["start_date", "end_date", "data_delivery_date", "po_date"]

DEALS_NUMERIC_FIELDS: List[str] = ["deal_value", "closure_probability"]
WORKORDERS_NUMERIC_FIELDS: List[str] = ["invoice_amount", "amount_receivable", "quantity"]
