"""
backend/helpers/evidence_builder.py

Assembles all deterministically computed metrics into a structured
EvidencePackage that is the ONLY thing passed to Fireworks AI.

Rules:
  - Only verified, Python-computed facts enter this package.
  - No inferred conclusions.
  - No invented numbers.
  - If data is missing, a warning is recorded and the metric is absent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.app.logger import get_logger
from backend.helpers.calculation_helper import format_currency, format_percentage
from backend.helpers.data_quality_helper import compute_deals_quality, compute_workorders_quality
from backend.helpers.pipeline_helper import compute_pipeline_kpis
from backend.helpers.revenue_helper import compute_revenue_kpis
from backend.helpers.workorder_helper import compute_workorder_kpis
from backend.helpers.time_intelligence_helper import (
    apply_time_filter,
    revenue_trend_mom,
    revenue_trend_qoq,
    revenue_trend_yoy,
    avg_deal_value_by_month,
    avg_deal_value_by_quarter,
    avg_deal_value_by_year,
    _effective_date_col,
)

logger = get_logger(__name__)

# Date columns to try (in priority order) for deals and work orders
DEALS_DATE_COLS = ["close_date", "tentative_close_date", "created_date"]
WO_DATE_COLS = ["start_date", "end_date", "data_delivery_date", "po_date"]


def build_evidence(
    deals_df: pd.DataFrame,
    wo_df: pd.DataFrame,
    *,
    # Time-intelligence parameters (all optional)
    period: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    quarter: Optional[int] = None,
    start_date=None,
    end_date=None,
    rolling_days: Optional[int] = None,
    rolling_months: Optional[int] = None,
    half: Optional[int] = None,
    # Trend flags
    trend_mom: bool = False,
    trend_qoq: bool = False,
    trend_yoy: bool = False,
    trend_avg_monthly: bool = False,
    trend_avg_quarterly: bool = False,
    trend_avg_yearly: bool = False,
    # Scope flags (which domains to compute)
    include_pipeline: bool = True,
    include_revenue: bool = True,
    include_workorders: bool = True,
    include_quality: bool = True,
) -> Dict[str, Any]:
    """
    Build and return a structured EvidencePackage.

    The package contains:
      facts           – bullet-point confirmed facts derived from metrics
      warnings        – data-quality or coverage notices
      recommendations – derived only from computed metrics (no guessing)
      metrics         – all computed KPIs keyed by domain
      data_quality    – per-board quality report
      computed_at     – ISO timestamp
      time_context    – what time filter (if any) was applied
    """
    computed_at = datetime.now(timezone.utc).isoformat()
    facts: List[str] = []
    warnings: List[str] = []
    recommendations: List[str] = []
    metrics: Dict[str, Any] = {}
    data_quality: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Apply time filter to deals_df if any time parameters were supplied
    # ------------------------------------------------------------------
    has_time_filter = any([
        period, year, month, quarter, start_date, end_date,
        rolling_days, rolling_months, half,
    ])

    filtered_deals = deals_df
    filtered_wo = wo_df
    time_context: Dict[str, Any] = {"applied": False}

    if has_time_filter:
        deals_date_col = _effective_date_col(deals_df, DEALS_DATE_COLS)
        wo_date_col = _effective_date_col(wo_df, WO_DATE_COLS)
        kwargs = dict(
            period=period, year=year, month=month, quarter=quarter,
            start_date=start_date, end_date=end_date,
            rolling_days=rolling_days, rolling_months=rolling_months,
            half=half,
        )
        if deals_date_col:
            filtered_deals = apply_time_filter(deals_df, deals_date_col, **kwargs)
        if wo_date_col:
            filtered_wo = apply_time_filter(wo_df, wo_date_col, **kwargs)

        time_context = {
            "applied": True,
            "period": period,
            "year": year,
            "month": month,
            "quarter": quarter,
            "start_date": str(start_date) if start_date else None,
            "end_date": str(end_date) if end_date else None,
            "rolling_days": rolling_days,
            "rolling_months": rolling_months,
            "half": half,
            "deals_filtered_count": len(filtered_deals),
            "wo_filtered_count": len(filtered_wo),
        }
        logger.info(
            f"Time filter applied: {len(filtered_deals)} deals, "
            f"{len(filtered_wo)} work orders in window."
        )
        if filtered_deals.empty and not deals_df.empty:
            warnings.append("No deals found in the requested time window.")
        if filtered_wo.empty and not wo_df.empty:
            warnings.append("No work orders found in the requested time window.")

    # ------------------------------------------------------------------
    # Pipeline KPIs
    # ------------------------------------------------------------------
    if include_pipeline:
        try:
            pipeline_kpis = compute_pipeline_kpis(filtered_deals)
            metrics["pipeline"] = pipeline_kpis

            # Facts
            facts.append(
                f"Open pipeline: {pipeline_kpis['open_pipeline_fmt']} "
                f"across {pipeline_kpis['open_deal_count']} open deals."
            )
            facts.append(f"Weighted pipeline: {pipeline_kpis['weighted_pipeline_fmt']}.")
            facts.append(
                f"Win ratio: {pipeline_kpis['win_ratio_fmt']} "
                f"({pipeline_kpis['won_deal_count']} won / "
                f"{pipeline_kpis['total_deal_count']} total)."
            )

            # Recommendations based on ratios
            if pipeline_kpis["win_ratio_pct"] < 20:
                recommendations.append(
                    "Win ratio is below 20% — review deal qualification and follow-up cadence."
                )
            if pipeline_kpis["loss_ratio_pct"] > 40:
                recommendations.append(
                    "Loss ratio exceeds 40% — investigate lost deal root causes."
                )
        except Exception as exc:
            warnings.append(f"Pipeline KPI computation failed: {exc}")
            logger.warning(f"Pipeline KPI error: {exc}")

    # ------------------------------------------------------------------
    # Revenue KPIs
    # ------------------------------------------------------------------
    if include_revenue:
        try:
            revenue_kpis = compute_revenue_kpis(filtered_deals)
            metrics["revenue"] = revenue_kpis

            facts.append(f"Total revenue: {revenue_kpis['total_revenue_fmt']}.")
            facts.append(f"Average revenue per deal: {revenue_kpis['average_revenue_fmt']}.")
            if revenue_kpis["top_customers"]:
                top = revenue_kpis["top_customers"][0]
                facts.append(
                    f"Top customer by revenue: {top.get('client_code', 'N/A')} "
                    f"({format_currency(top.get('total_revenue', 0))})."
                )
        except Exception as exc:
            warnings.append(f"Revenue KPI computation failed: {exc}")
            logger.warning(f"Revenue KPI error: {exc}")

    # ------------------------------------------------------------------
    # Work Order KPIs
    # ------------------------------------------------------------------
    if include_workorders:
        try:
            wo_kpis = compute_workorder_kpis(filtered_wo)
            metrics["work_orders"] = wo_kpis

            facts.append(f"Total invoiced: {wo_kpis['total_invoiced_fmt']}.")
            facts.append(f"Total pending receivable: {wo_kpis['total_receivable_fmt']}.")
            if wo_kpis["past_due_count"] > 0:
                facts.append(f"{wo_kpis['past_due_count']} work orders are past their end date and not yet completed.")

            # Recommendations
            if wo_kpis["past_due_count"] > 5:
                recommendations.append(
                    f"{wo_kpis['past_due_count']} work orders are overdue — "
                    "prioritize operational review this week."
                )
            if wo_kpis["total_receivable"] > wo_kpis["total_invoiced"] * 0.3:
                recommendations.append(
                    "Receivables exceed 30% of total invoiced — accelerate collections."
                )
        except Exception as exc:
            warnings.append(f"Work Order KPI computation failed: {exc}")
            logger.warning(f"Work Order KPI error: {exc}")

    # ------------------------------------------------------------------
    # Data Quality
    # ------------------------------------------------------------------
    if include_quality:
        try:
            deals_quality = compute_deals_quality(deals_df)  # always on unfiltered
            wo_quality = compute_workorders_quality(wo_df)
            data_quality = {"deals": deals_quality, "work_orders": wo_quality}
            warnings.extend(deals_quality.get("warnings", []))
            warnings.extend(wo_quality.get("warnings", []))
        except Exception as exc:
            warnings.append(f"Data quality check failed: {exc}")
            logger.warning(f"Data quality error: {exc}")

    # ------------------------------------------------------------------
    # Time-intelligence trends
    # ------------------------------------------------------------------
    trend_date_col = _effective_date_col(deals_df, DEALS_DATE_COLS)
    if trend_date_col:
        if trend_mom:
            try:
                metrics["trend_mom"] = revenue_trend_mom(deals_df, trend_date_col)
                facts.append("Month-over-month revenue trend computed (last 12 months).")
            except Exception as exc:
                warnings.append(f"MoM trend failed: {exc}")

        if trend_qoq:
            try:
                metrics["trend_qoq"] = revenue_trend_qoq(deals_df, trend_date_col)
                facts.append("Quarter-over-quarter revenue trend computed (last 8 quarters).")
            except Exception as exc:
                warnings.append(f"QoQ trend failed: {exc}")

        if trend_yoy:
            try:
                metrics["trend_yoy"] = revenue_trend_yoy(deals_df, trend_date_col)
                facts.append("Year-over-year revenue trend computed (last 5 years).")
            except Exception as exc:
                warnings.append(f"YoY trend failed: {exc}")

        if trend_avg_monthly:
            try:
                metrics["avg_deal_by_month"] = avg_deal_value_by_month(deals_df, trend_date_col)
            except Exception as exc:
                warnings.append(f"Avg deal by month failed: {exc}")

        if trend_avg_quarterly:
            try:
                metrics["avg_deal_by_quarter"] = avg_deal_value_by_quarter(deals_df, trend_date_col)
            except Exception as exc:
                warnings.append(f"Avg deal by quarter failed: {exc}")

        if trend_avg_yearly:
            try:
                metrics["avg_deal_by_year"] = avg_deal_value_by_year(deals_df, trend_date_col)
            except Exception as exc:
                warnings.append(f"Avg deal by year failed: {exc}")
    else:
        if any([trend_mom, trend_qoq, trend_yoy, trend_avg_monthly, trend_avg_quarterly, trend_avg_yearly]):
            warnings.append("Trend analysis requested but no date column is available in the deals data.")

    # ------------------------------------------------------------------
    # Deduplicate warnings
    # ------------------------------------------------------------------
    warnings = list(dict.fromkeys(warnings))

    logger.info(
        f"Evidence built: {len(facts)} facts, {len(warnings)} warnings, "
        f"{len(recommendations)} recommendations, {len(metrics)} metric domains."
    )

    return {
        "facts": facts,
        "warnings": warnings,
        "recommendations": recommendations,
        "metrics": metrics,
        "data_quality": data_quality,
        "time_context": time_context,
        "computed_at": computed_at,
    }
