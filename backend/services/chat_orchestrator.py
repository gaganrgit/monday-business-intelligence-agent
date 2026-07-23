"""
Chat orchestrator.

Coordinates the full request pipeline for a single /chat call:

  1. Fetch fresh data from monday.com (MondayService)
  2. Clean it (utils.data_cleaning)
  3. Understand the question (utils.query_understanding)
  4. Run sector / date filters (analytics.analytics_engine helpers)
  5. Run the Business Computation Layer (helpers.evidence_builder)
  6. Send structured evidence to Fireworks AI (services.fireworks_service)
  7. Return a founder-friendly answer

Kept intentionally simple and linear -- no agent frameworks, no
multi-step planning loops.
"""

import time
from typing import Any, Dict

from backend.analytics import analytics_engine as ae
from backend.app.logger import get_logger
from backend.helpers.evidence_builder import build_evidence
from backend.services.fireworks_service import FireworksService, FireworksServiceError
from backend.services.monday_service import MondayService, MondayServiceError
from backend.utils.data_cleaning import clean_deals, clean_work_orders
from backend.utils.query_understanding import parse_query

logger = get_logger(__name__)


class ChatOrchestrator:
    def __init__(self) -> None:
        self.monday_service = MondayService()
        self.fireworks_service = FireworksService()

    def _load_clean_data(self):
        """Fetch and clean both boards. Raises MondayServiceError on failure."""
        from backend.app.config import settings

        deals_raw = self.monday_service.fetch_board_items(settings.deals_board_id, "Deals")
        wo_raw = self.monday_service.fetch_board_items(settings.workorders_board_id, "Work Orders")

        deals_df, deals_quality = clean_deals(deals_raw)
        wo_df, wo_quality = clean_work_orders(wo_raw)

        return deals_df, wo_df, deals_quality, wo_quality

    def handle_message(self, message: str) -> str:
        start_time = time.time()
        logger.info(f"Incoming Question: {message}")

        parsed = parse_query(message)
        logger.info(f"Detected Intent: {parsed.intents}")

        if parsed.needs_clarification:
            logger.info(f"Execution Time: {round(time.time() - start_time, 2)}s")
            return parsed.clarification_question

        try:
            deals_df, wo_df, deals_quality, wo_quality = self._load_clean_data()
        except MondayServiceError as exc:
            logger.error(f"Monday.com integration failure: {exc}")
            return f"I couldn't retrieve live data from monday.com right now. {exc}"

        # ------------------------------------------------------------------
        # Sector filter (unchanged — applied before evidence builder)
        # ------------------------------------------------------------------
        if parsed.sector:
            deals_df = ae.filter_by_sector(deals_df, parsed.sector)
            wo_df = ae.filter_by_sector(wo_df, parsed.sector)

        # ------------------------------------------------------------------
        # Determine which KPI domains are needed for this query
        # ------------------------------------------------------------------
        intents = set(parsed.intents)
        include_pipeline = bool(
            intents & {
                "pipeline", "revenue", "sector_performance", "deals_by_stage",
                "upcoming_closures", "customer_lookup", "leadership_update",
                "time_intelligence",
            }
        )
        include_revenue = bool(
            intents & {
                "revenue", "sector_performance", "customer_lookup",
                "leadership_update", "time_intelligence",
            }
        )
        include_workorders = bool(
            intents & {
                "delayed_work_orders", "execution_summary", "billing_summary",
                "pending_receivables", "collection_summary", "customer_lookup",
                "leadership_update",
            }
        )
        # Always include at least pipeline + revenue for generic questions
        if not include_pipeline and not include_revenue and not include_workorders:
            include_pipeline = True
            include_revenue = True

        # ------------------------------------------------------------------
        # Business Computation Layer
        # All arithmetic, aggregation, KPI computation, and date/time
        # reasoning happens here — the LLM never touches numbers.
        # ------------------------------------------------------------------
        logger.info("Building Evidence Package via Business Computation Layer...")
        evidence = build_evidence(
            deals_df,
            wo_df,
            # Time-intelligence parameters extracted by query parser
            period=parsed.period,
            year=parsed.year,
            month=parsed.month,
            quarter=parsed.quarter,
            start_date=parsed.start_date,
            end_date=parsed.end_date,
            rolling_days=parsed.rolling_days,
            rolling_months=parsed.rolling_months,
            half=parsed.half,
            # Trend flags
            trend_mom=parsed.trend_mom,
            trend_qoq=parsed.trend_qoq,
            trend_yoy=parsed.trend_yoy,
            trend_avg_monthly=parsed.trend_avg_monthly,
            trend_avg_quarterly=parsed.trend_avg_quarterly,
            trend_avg_yearly=parsed.trend_avg_yearly,
            # Scope
            include_pipeline=include_pipeline,
            include_revenue=include_revenue,
            include_workorders=include_workorders,
            include_quality=True,
        )
        logger.info(
            f"Evidence Built: {len(evidence['facts'])} facts | "
            f"{len(evidence['warnings'])} warnings | "
            f"{len(evidence['recommendations'])} recommendations"
        )

        # ------------------------------------------------------------------
        # Fireworks AI — receives ONLY verified structured evidence,
        # never raw DataFrames or analytics dicts.
        # ------------------------------------------------------------------
        try:
            answer = self.fireworks_service.generate_insight(
                question=message,
                evidence=evidence,
            )
        except FireworksServiceError as exc:
            logger.error(f"Fireworks Error: {exc}")
            answer = self._fallback_answer(evidence)

        logger.info("Response Generated")
        logger.info(f"Execution Time: {round(time.time() - start_time, 2)}s")
        return answer

    @staticmethod
    def _fallback_answer(evidence: Dict[str, Any]) -> str:
        """Deterministic fallback used only if Fireworks is unreachable."""
        parts = ["I couldn't reach the AI service, but here is what I computed:"]
        for fact in evidence.get("facts", []):
            parts.append(f"• {fact}")
        for warning in evidence.get("warnings", []):
            parts.append(f"⚠ {warning}")
        for rec in evidence.get("recommendations", []):
            parts.append(f"→ {rec}")
        return "\n".join(parts)
