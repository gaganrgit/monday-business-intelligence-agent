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

from datetime import date, datetime, timezone
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
# Pipeline date priority: tentative_close_date is preferred because many open
# deals lack an actual close_date, so filtering on close_date first would drop
# most of the active pipeline.
DEALS_DATE_COLS = ["tentative_close_date", "close_date", "created_date"]
WO_DATE_COLS = ["start_date", "end_date", "data_delivery_date", "po_date"]


def build_evidence(
    deals_df: pd.DataFrame,
    wo_df: pd.DataFrame,
    *,
    # Dual-gate: filter is ONLY applied when both this flag is True AND at least
    # one explicit time param (year/month/quarter/period/…) is non-None.
    # This prevents parser-default values from silently triggering a time filter.
    has_time_intent: bool = False,
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
    logger.info("=================== [EVIDENCE BUILDER] ===================")
    logger.info(
        f"Input DataFrame Shapes: Deals = {deals_df.shape}, Work Orders = {wo_df.shape} | "
        f"Scope: pipeline={include_pipeline}, revenue={include_revenue}, "
        f"workorders={include_workorders}, quality={include_quality}"
    )

    computed_at = datetime.now(timezone.utc).isoformat()
    facts: List[str] = []
    warnings: List[str] = []
    recommendations: List[str] = []
    metrics: Dict[str, Any] = {}
    data_quality: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Apply time filter — dual-gate:
    #   Gate 1: caller must declare time_intelligence intent.
    #   Gate 2: at least one explicit time parameter must be present.
    # Both must be true; either alone is insufficient.
    # ------------------------------------------------------------------
    has_explicit_time_params = any([
        period, year, month, quarter, start_date, end_date,
        rolling_days, rolling_months, half,
    ])
    has_time_filter = has_time_intent and has_explicit_time_params

    logger.info(
        f"Time Filter Gate: has_time_intent={has_time_intent}, "
        f"has_explicit_time_params={has_explicit_time_params} "
        f"=> applying_filter={has_time_filter}"
    )
    if has_explicit_time_params and not has_time_intent:
        logger.warning(
            "VALIDATION WARNING: Explicit time params present but 'time_intelligence' intent "
            "was NOT set — time filter suppressed (dual-gate protection). "
            f"Params: period={period}, year={year}, month={month}, quarter={quarter}, "
            f"half={half}, rolling_days={rolling_days}, rolling_months={rolling_months}."
        )

    filtered_deals = deals_df
    filtered_wo = wo_df
    time_context: Dict[str, Any] = {"applied": False}

    if has_time_filter:
        deals_date_col = _effective_date_col(deals_df, DEALS_DATE_COLS)
        wo_date_col = _effective_date_col(wo_df, WO_DATE_COLS)

        # --- Fix 4: Log date column statistics before filtering ---
        for label, df_ref, col in [
            ("Deals", deals_df, deals_date_col),
            ("Work Orders", wo_df, wo_date_col),
        ]:
            if col and col in df_ref.columns:
                series = df_ref[col]
                non_null = series.notna().sum()
                null_count = series.isna().sum()
                col_min = series.dropna().min() if non_null > 0 else "N/A"
                col_max = series.dropna().max() if non_null > 0 else "N/A"
                logger.info(
                    f"Date Column Stats [{label}] '{col}': "
                    f"non_null={non_null}, null={null_count}, "
                    f"min={col_min}, max={col_max}"
                )

        kwargs = dict(
            period=period, year=year, month=month, quarter=quarter,
            start_date=start_date, end_date=end_date,
            rolling_days=rolling_days, rolling_months=rolling_months,
            half=half,
        )
        if deals_date_col:
            filtered_deals = apply_time_filter(deals_df, deals_date_col, **kwargs)
        else:
            logger.warning("VALIDATION WARNING: Time filter requested for Deals, but no valid date column was found.")

        if wo_date_col:
            filtered_wo = apply_time_filter(wo_df, wo_date_col, **kwargs)
        else:
            logger.warning("VALIDATION WARNING: Time filter requested for Work Orders, but no valid date column was found.")

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
            f"Time Filter Results: {len(deals_df)} -> {len(filtered_deals)} Deals | "
            f"{len(wo_df)} -> {len(filtered_wo)} Work Orders"
        )

        # ------------------------------------------------------------------
        # Smart fallback: if the time window returns zero rows for ALL boards
        # that had data, fall back to the full dataset and warn the user.
        # This prevents the LLM from seeing a completely empty evidence package
        # just because the requested period has no records yet (e.g. querying
        # Q3 when all deals close in Q1/Q2).
        # ------------------------------------------------------------------
        deals_empty_after_filter = filtered_deals.empty and not deals_df.empty
        wo_empty_after_filter = filtered_wo.empty and not wo_df.empty

        if deals_empty_after_filter:
            warnings.append("No deals found in the requested time window.")
            logger.warning("VALIDATION WARNING: Filtered deals DataFrame is empty after time filtering.")
        if wo_empty_after_filter:
            warnings.append("No work orders found in the requested time window.")
            logger.warning("VALIDATION WARNING: Filtered work orders DataFrame is empty after time filtering.")

        # If every scoped board is empty after filtering, fall back to all data
        scoped_deals_empty = deals_empty_after_filter and (include_pipeline or include_revenue)
        scoped_wo_empty = wo_empty_after_filter and include_workorders
        all_scoped_empty = (
            (scoped_deals_empty or not (include_pipeline or include_revenue))
            and (scoped_wo_empty or not include_workorders)
        )

        if all_scoped_empty or (deals_empty_after_filter and not include_workorders):
            logger.warning(
                "VALIDATION WARNING: Time filter returned no data for any scoped domain. "
                "Falling back to full dataset to provide useful metrics."
            )
            fallback_period = period or (
                f"Q{quarter} {date.today().year}" if quarter else
                str(year) if year else "requested period"
            )
            # Compute the latest available date for a helpful message
            _fb_date_col = _effective_date_col(deals_df, DEALS_DATE_COLS)
            if _fb_date_col and _fb_date_col in deals_df.columns:
                _latest = deals_df[_fb_date_col].dropna().max()
                _latest_str = str(_latest) if _latest is not None else "unknown"
            else:
                _latest_str = "unknown"
            warnings.append(
                f"No data exists for the {fallback_period}. Showing all available data instead. "
                f"Latest deal close date on record is {_latest_str}."
            )
            filtered_deals = deals_df
            filtered_wo = wo_df
            time_context["fallback_to_all_data"] = True
            time_context["fallback_reason"] = f"No records in {fallback_period}"
        else:
            time_context["fallback_to_all_data"] = False

    # ------------------------------------------------------------------
    # Pipeline KPIs
    # ------------------------------------------------------------------
    if include_pipeline:
        logger.info("=================== [PIPELINE VALIDATION] ===================")
        logger.info(f"Deals Input Rows: {len(filtered_deals)}")
        try:
            pipeline_kpis = compute_pipeline_kpis(filtered_deals)
            metrics["pipeline"] = pipeline_kpis

            logger.info(
                f"Computed Pipeline Metrics: Open Pipeline = {pipeline_kpis['open_pipeline_fmt']} "
                f"({pipeline_kpis['open_deal_count']} deals), Weighted = {pipeline_kpis['weighted_pipeline_fmt']}, "
                f"Win Ratio = {pipeline_kpis['win_ratio_fmt']}"
            )

            if not filtered_deals.empty and pipeline_kpis["open_pipeline"] == 0.0:
                logger.warning("VALIDATION WARNING: Non-empty Deals DataFrame yielded 0.0 open pipeline value.")

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
            logger.error(f"VALIDATION ERROR: Pipeline KPI computation failed: {exc}")

    # ------------------------------------------------------------------
    # Revenue KPIs
    # ------------------------------------------------------------------
    if include_revenue:
        logger.info("=================== [REVENUE VALIDATION] ===================")
        logger.info(f"Deals Input Rows for Revenue: {len(filtered_deals)}")
        try:
            revenue_kpis = compute_revenue_kpis(filtered_deals)
            metrics["revenue"] = revenue_kpis

            logger.info(
                f"Computed Revenue Metrics: Total Revenue = {revenue_kpis['total_revenue_fmt']}, "
                f"Avg Revenue/Deal = {revenue_kpis['average_revenue_fmt']}"
            )

            if not filtered_deals.empty and revenue_kpis["total_revenue"] == 0.0:
                logger.warning("VALIDATION WARNING: Non-empty Deals DataFrame yielded 0.0 total revenue.")

            facts.append(f"Total revenue: {revenue_kpis['total_revenue_fmt']}.")
            facts.append(f"Average revenue per deal: {revenue_kpis['average_revenue_fmt']}.")
            if revenue_kpis["top_customers"]:
                top = revenue_kpis["top_customers"][0]
                facts.append(
                    f"Top customer by revenue: {top.get('client_code', 'N/A')} "
                    f"({format_currency(top.get('total_revenue', 0))})."
                )
                top_3_cust = [
                    f"{c.get('client_code')}: {format_currency(c.get('total_revenue', 0))}"
                    for c in revenue_kpis["top_customers"][:3]
                ]
                facts.append(f"Top 3 customers by revenue: {', '.join(top_3_cust)}.")
            if revenue_kpis.get("revenue_by_sector"):
                top_sec = revenue_kpis["revenue_by_sector"][0]
                sec_name = top_sec.get("sector") or top_sec.get("group_column") or "Unspecified"
                sec_val = top_sec.get("total_revenue") or top_sec.get("deal_value") or 0.0
                facts.append(
                    f"Top performing sector: {sec_name} ({format_currency(sec_val)} total deal revenue)."
                )
                metrics["sector_performance"] = revenue_kpis["revenue_by_sector"]
        except Exception as exc:
            warnings.append(f"Revenue KPI computation failed: {exc}")
            logger.error(f"VALIDATION ERROR: Revenue KPI computation failed: {exc}")

    # ------------------------------------------------------------------
    # Work Order KPIs
    # ------------------------------------------------------------------
    if include_workorders:
        logger.info("=================== [WORK ORDER VALIDATION] ===================")
        logger.info(f"Work Orders Input Rows: {len(filtered_wo)}")
        try:
            wo_kpis = compute_workorder_kpis(filtered_wo)
            metrics["work_orders"] = wo_kpis

            logger.info(
                f"Computed Work Order Metrics: Total Invoiced = {wo_kpis['total_invoiced_fmt']}, "
                f"Pending Receivables = {wo_kpis['total_receivable_fmt']}, Overdue Count = {wo_kpis['past_due_count']}"
            )

            if not filtered_wo.empty and wo_kpis["total_invoiced"] == 0.0:
                logger.warning("VALIDATION WARNING: Non-empty Work Orders DataFrame yielded 0.0 total invoiced amount.")

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
            logger.error(f"VALIDATION ERROR: Work Order KPI computation failed: {exc}")

    # ------------------------------------------------------------------
    # Cross-Board Analytics
    # ------------------------------------------------------------------
    if include_pipeline and include_workorders:
        logger.info("=================== [CROSS-BOARD VALIDATION] ===================")
        try:
            from backend.analytics.analytics_engine import cross_board_customer_lookup
            at_risk = cross_board_customer_lookup(filtered_deals, filtered_wo)
            metrics["at_risk_customers"] = at_risk
            if at_risk:
                top_risk = at_risk[0]
                facts.append(
                    f"Cross-board analysis: {len(at_risk)} customers have active deals AND delayed work orders "
                    f"(e.g., {top_risk['customer_code']} with {top_risk['active_deal_count']} active deal(s) "
                    f"worth {format_currency(top_risk['active_deal_value'])} and {top_risk['delayed_work_order_count']} delayed work order(s))."
                )
                recommendations.append(
                    f"Review operational status for at-risk accounts ({len(at_risk)} customers have active deals alongside delayed work orders)."
                )
        except Exception as exc:
            warnings.append(f"Cross-board customer analysis failed: {exc}")
            logger.error(f"VALIDATION ERROR: Cross-board analysis failed: {exc}")

    # ------------------------------------------------------------------
    # Data Quality
    # ------------------------------------------------------------------
    if include_quality:
        logger.info("=================== [DATA QUALITY VALIDATION] ===================")
        try:
            deals_quality = compute_deals_quality(deals_df)  # always on unfiltered
            wo_quality = compute_workorders_quality(wo_df)
            data_quality = {"deals": deals_quality, "work_orders": wo_quality}
            warnings.extend(deals_quality.get("warnings", []))
            warnings.extend(wo_quality.get("warnings", []))

            if deals_quality.get("duplicate_clients_list"):
                dups_str = ", ".join([f"{item['value']} ({item['count']} deals)" for item in deals_quality["duplicate_clients_list"][:5]])
                facts.append(f"Deals board duplicate client codes: {dups_str}.")

            if wo_quality.get("duplicate_customers_list"):
                dups_str = ", ".join([f"{item['value']} ({item['count']} work orders)" for item in wo_quality["duplicate_customers_list"][:5]])
                facts.append(f"Work Orders board duplicate customer codes: {dups_str}.")
        except Exception as exc:
            warnings.append(f"Data quality check failed: {exc}")
            logger.error(f"VALIDATION ERROR: Data quality check failed: {exc}")

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
            logger.warning("VALIDATION WARNING: Trend analysis requested but no date column is available.")

    # ------------------------------------------------------------------
    # Deduplicate warnings
    # ------------------------------------------------------------------
    warnings = list(dict.fromkeys(warnings))

    logger.info("=================== [EVIDENCE PACKAGE SUMMARY] ===================")
    logger.info(
        f"Evidence Package Assembled: {len(facts)} facts | {len(warnings)} warnings | "
        f"{len(recommendations)} recommendations | Metric Domains = {list(metrics.keys())}"
    )
    for i, fact in enumerate(facts, 1):
        logger.info(f"  Fact #{i}: {fact}")
    for i, warn in enumerate(warnings, 1):
        logger.warning(f"  Warning #{i}: {warn}")
    for i, rec in enumerate(recommendations, 1):
        logger.info(f"  Recommendation #{i}: {rec}")

    return {
        "facts": facts,
        "warnings": warnings,
        "recommendations": recommendations,
        "metrics": metrics,
        "data_quality": data_quality,
        "time_context": time_context,
        "computed_at": computed_at,
    }
