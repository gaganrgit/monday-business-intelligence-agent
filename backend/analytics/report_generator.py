"""
Leadership Update report generator.

Builds a full analytics summary across both boards, asks Fireworks AI
to write the narrative sections, and assembles everything into a
single Markdown report with the sections required by the assignment.
"""

from datetime import date
from typing import Any, Dict

import pandas as pd

from backend.analytics import analytics_engine as ae
from backend.app.logger import get_logger
from backend.services.fireworks_service import FireworksService, FireworksServiceError

logger = get_logger(__name__)

REPORT_SECTIONS = [
    "Executive Summary",
    "Revenue Overview",
    "Pipeline Health",
    "Sector Performance",
    "Operational Status",
    "Billing & Collections",
    "Risks",
    "Recommendations",
    "Data Quality Notes",
]


def build_full_analytics_summary(
    deals_df: pd.DataFrame,
    wo_df: pd.DataFrame,
    deals_quality: Dict[str, Any],
    wo_quality: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute every metric needed for a comprehensive leadership report."""
    return {
        "generated_on": str(date.today()),
        "total_pipeline_all": ae.total_pipeline_value(deals_df, only_open=False),
        "total_pipeline_open": ae.total_pipeline_value(deals_df, only_open=True),
        "revenue_by_sector": ae.revenue_by_sector(deals_df),
        "deals_by_stage": ae.deals_by_stage(deals_df),
        "pipeline_by_probability": ae.pipeline_by_probability(deals_df),
        "upcoming_closures": ae.upcoming_closures(deals_df),
        "delayed_work_orders": ae.delayed_work_orders(wo_df),
        "execution_summary": ae.execution_summary(wo_df),
        "billing_summary": ae.billing_summary(wo_df),
        "pending_receivables": ae.pending_receivables(wo_df),
        "collection_summary": ae.collection_summary(wo_df),
        "at_risk_customers": ae.cross_board_customer_lookup(deals_df, wo_df),
        "data_quality": {
            "deals": deals_quality,
            "work_orders": wo_quality,
        },
    }


def generate_leadership_report_markdown(
    deals_df: pd.DataFrame,
    wo_df: pd.DataFrame,
    deals_quality: Dict[str, Any],
    wo_quality: Dict[str, Any],
    fireworks_service: FireworksService,
) -> str:
    """Generate the full Markdown leadership report."""
    logger.info("Running Analytics...")
    summary = build_full_analytics_summary(deals_df, wo_df, deals_quality, wo_quality)
    logger.info("Revenue Calculated")
    logger.info("Pipeline Calculated")

    instructions = (
        "Write a leadership update using ONLY the JSON analytics above. "
        "Structure your response with EXACTLY these Markdown headings (## level), "
        "in this order, and nothing else:\n"
        + "\n".join(f"## {s}" for s in REPORT_SECTIONS)
        + "\n\nUnder each heading write 2-5 concise sentences or bullet points. "
        "Under 'Data Quality Notes', explicitly mention the missing_values, "
        "invalid_dates, and skipped_records counts from the data_quality section, "
        "and note if data quality is poor. "
        "Always use the Indian Rupee symbol (₹) for monetary values. Do NOT use € or $."
    )

    try:
        narrative = fireworks_service.generate_insight(
            question="Generate the leadership update report.",
            analytics_summary=summary,
            extra_instructions=instructions,
        )
    except FireworksServiceError as exc:
        logger.error(f"Fireworks Error while generating leadership report: {exc}")
        narrative = _fallback_report(summary)

    header = f"# Leadership Update — {date.today().strftime('%B %d, %Y')}\n\n"
    logger.info("Leadership Report Generated")
    return header + narrative


def _fallback_report(summary: Dict[str, Any]) -> str:
    """A deterministic, non-LLM report used only if Fireworks is unavailable,
    so the /leadership-summary endpoint still returns something useful."""
    lines = []
    lines.append("## Executive Summary")
    lines.append(
        f"- Open pipeline value: {summary['total_pipeline_open']['total_value']} "
        f"across {summary['total_pipeline_open']['deal_count']} deals."
    )
    lines.append("\n## Revenue Overview")
    for s in summary["revenue_by_sector"][:5]:
        lines.append(f"- {s['sector']}: {s['total_value']} ({s['deal_count']} deals)")
    lines.append("\n## Pipeline Health")
    lines.append(f"- Weighted pipeline: {summary['pipeline_by_probability']['weighted_pipeline']}")
    lines.append("\n## Sector Performance")
    for s in summary["revenue_by_sector"][:5]:
        lines.append(f"- {s['sector']}: {s['total_value']}")
    lines.append("\n## Operational Status")
    for s in summary["execution_summary"]:
        lines.append(f"- {s['status']}: {s['count']}")
    lines.append("\n## Billing & Collections")
    lines.append(f"- Total invoiced: {summary['billing_summary']['total_invoiced']}")
    lines.append(f"- Total receivable: {summary['pending_receivables']['total_receivable']}")
    lines.append("\n## Risks")
    lines.append(f"- Delayed work orders: {len(summary['delayed_work_orders'])}")
    lines.append(f"- At-risk customers (active deal + delayed work): {len(summary['at_risk_customers'])}")
    lines.append("\n## Recommendations")
    lines.append("- Review delayed work orders and at-risk customer accounts this week.")
    lines.append("\n## Data Quality Notes")
    dq = summary["data_quality"]
    lines.append(
        f"- Deals: {dq['deals'].get('missing_values', 0)} missing values, "
        f"{dq['deals'].get('invalid_dates', 0)} invalid dates, "
        f"{dq['deals'].get('skipped_records', 0)} skipped records."
    )
    lines.append(
        f"- Work Orders: {dq['work_orders'].get('missing_values', 0)} missing values, "
        f"{dq['work_orders'].get('invalid_dates', 0)} invalid dates, "
        f"{dq['work_orders'].get('skipped_records', 0)} skipped records."
    )
    lines.append(
        "\n_Note: This report was generated using deterministic fallback formatting "
        "because the AI narrative service was unavailable._"
    )
    return "\n".join(lines)
