"""
Chat orchestrator.

Coordinates the full request pipeline for a single /chat call:

  1. Fetch fresh data from monday.com (MondayService)
  2. Clean it (utils.data_cleaning)
  3. Understand the question (utils.query_understanding)
  4. Run the relevant analytics functions (analytics.analytics_engine)
  5. Summarize + send to Fireworks AI (services.fireworks_service)
  6. Return a founder-friendly answer

Kept intentionally simple and linear -- no agent frameworks, no
multi-step planning loops.
"""

import time
from typing import Any, Dict

from backend.analytics import analytics_engine as ae
from backend.app.logger import get_logger
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

        if parsed.sector:
            deals_df = ae.filter_by_sector(deals_df, parsed.sector)
            wo_df = ae.filter_by_sector(wo_df, parsed.sector)

        summary = self._build_summary_for_intents(parsed, deals_df, wo_df)
        summary["data_quality"] = {"deals": deals_quality, "work_orders": wo_quality}
        summary["filters_applied"] = {
            "sector": parsed.sector,
            "quarter": parsed.quarter,
            "only_open": parsed.only_open,
        }

        poor_quality = (
            deals_quality.get("skipped_records", 0) > 0
            or wo_quality.get("skipped_records", 0) > 0
            or deals_quality.get("invalid_dates", 0) > 3
            or wo_quality.get("invalid_dates", 0) > 3
        )
        extra_instructions = (
            "Note: some records had data quality issues and were skipped or had "
            "invalid dates -- mention this briefly to the founder."
            if poor_quality
            else ""
        )

        try:
            answer = self.fireworks_service.generate_insight(
                question=message, analytics_summary=summary, extra_instructions=extra_instructions
            )
        except FireworksServiceError as exc:
            logger.error(f"Fireworks Error: {exc}")
            answer = self._fallback_answer(summary)

        logger.info("Response Generated")
        logger.info(f"Execution Time: {round(time.time() - start_time, 2)}s")
        return answer

    @staticmethod
    def _build_summary_for_intents(parsed, deals_df, wo_df) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}
        intents = set(parsed.intents)

        if "pipeline" in intents or "revenue" in intents:
            summary["total_pipeline"] = ae.total_pipeline_value(
                deals_df, only_open=parsed.only_open if parsed.only_open is not None else True
            )
        if "revenue" in intents or "sector_performance" in intents:
            summary["revenue_by_sector"] = ae.revenue_by_sector(deals_df)
        if "deals_by_stage" in intents:
            summary["deals_by_stage"] = ae.deals_by_stage(deals_df)
        if "pipeline" in intents:
            summary["pipeline_by_probability"] = ae.pipeline_by_probability(deals_df)
        if "upcoming_closures" in intents:
            summary["upcoming_closures"] = ae.upcoming_closures(deals_df)
        if "delayed_work_orders" in intents or "customer_lookup" in intents:
            summary["delayed_work_orders"] = ae.delayed_work_orders(wo_df)
        if "execution_summary" in intents:
            summary["execution_summary"] = ae.execution_summary(wo_df)
        if "billing_summary" in intents:
            summary["billing_summary"] = ae.billing_summary(wo_df)
        if "pending_receivables" in intents:
            summary["pending_receivables"] = ae.pending_receivables(wo_df)
        if "collection_summary" in intents:
            summary["collection_summary"] = ae.collection_summary(wo_df)
        if "customer_lookup" in intents:
            summary["cross_board_customer_lookup"] = ae.cross_board_customer_lookup(deals_df, wo_df)

        # Always guarantee at least something to work with.
        if not summary:
            summary["total_pipeline"] = ae.total_pipeline_value(deals_df, only_open=True)
            summary["revenue_by_sector"] = ae.revenue_by_sector(deals_df)

        return summary

    @staticmethod
    def _fallback_answer(summary: Dict[str, Any]) -> str:
        """Deterministic fallback used only if Fireworks is unreachable."""
        parts = ["I couldn't reach the AI service, but here is the raw data I found:"]
        for key, value in summary.items():
            if key in ("data_quality", "filters_applied"):
                continue
            parts.append(f"\n**{key.replace('_', ' ').title()}**: {value}")
        return "\n".join(parts)
