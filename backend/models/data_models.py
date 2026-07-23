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
    "client_code": ["client code", "client", "customer code", "customer"],
    "deal_status": ["deal status", "status"],
    "deal_stage": ["deal stage", "stage"],
    "deal_value": ["deal value", "value", "amount"],
    "closure_probability": ["closure probability", "probability", "close probability"],
    "close_date": ["close date", "closed date"],
    "tentative_close_date": ["tentative close date", "expected close date", "tentative close"],
    "product": ["product"],
    "sector": ["sector", "industry"],
    "created_date": ["created date", "created at", "creation date"],
}

# Work Orders board -- canonical field name -> aliases
WORKORDERS_FIELD_ALIASES = {
    "deal_name": ["deal name", "name", "deal"],
    "customer_code": ["customer code", "customer", "client code", "client"],
    "nature_of_work": ["nature of work", "work nature", "type of work"],
    "execution_status": ["execution status", "status"],
    "start_date": ["start date"],
    "end_date": ["end date"],
    "data_delivery_date": ["data delivery date", "delivery date"],
    "po_date": ["po date", "purchase order date"],
    "sector": ["sector", "industry"],
    "work_type": ["work type"],
    "invoice_amount": ["invoice amount", "invoice value"],
    "amount_receivable": ["amount receivable", "receivable amount", "receivable"],
    "billing_status": ["billing status"],
    "collection_status": ["collection status"],
    "quantity": ["quantity", "qty"],
    "invoice_status": ["invoice status"],
}

DEALS_DATE_FIELDS: List[str] = ["close_date", "tentative_close_date", "created_date"]
WORKORDERS_DATE_FIELDS: List[str] = ["start_date", "end_date", "data_delivery_date", "po_date"]

DEALS_NUMERIC_FIELDS: List[str] = ["deal_value", "closure_probability"]
WORKORDERS_NUMERIC_FIELDS: List[str] = ["invoice_amount", "amount_receivable", "quantity"]
