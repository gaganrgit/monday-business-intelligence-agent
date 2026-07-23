"""
Monday Business Intelligence Agent -- FastAPI backend.

Exposes:
  POST /chat                -> {"answer": "..."}
  GET  /leadership-summary  -> raw Markdown report
  GET  /health              -> service configuration status

This file only wires HTTP routes to the ChatOrchestrator / report
generator. All business logic lives in backend/services,
backend/analytics, and backend/utils.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from backend.app.config import settings
from backend.app.logger import get_logger
from backend.app.schemas import ChatRequest, ChatResponse, HealthResponse
from backend.analytics.report_generator import generate_leadership_report_markdown
from backend.services.chat_orchestrator import ChatOrchestrator
from backend.services.fireworks_service import FireworksService
from backend.services.monday_service import MondayService, MondayServiceError
from backend.utils.data_cleaning import clean_deals, clean_work_orders

logger = get_logger(__name__)

app = FastAPI(
    title="Monday Business Intelligence Agent",
    description="Conversational founder-level BI assistant backed by live monday.com data.",
    version="1.0.0",
)

# CORS is permissive because Streamlit and FastAPI are deployed together
# as a single Render service, but this keeps local development flexible too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = ChatOrchestrator()


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("✓ FastAPI Started")
    logger.info("✓ Environment Variables Loaded")
    if not settings.monday_api_token:
        logger.warning("MONDAY_API_TOKEN is not set -- monday.com calls will fail.")
    if not settings.fireworks_api_key:
        logger.warning("FIREWORKS_API_KEY is not set -- AI responses will fail.")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        monday_configured=bool(settings.monday_api_token and settings.deals_board_id and settings.workorders_board_id),
        fireworks_configured=bool(settings.fireworks_api_key),
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Answer a founder's natural-language business question."""
    try:
        answer = orchestrator.handle_message(request.message)
        return ChatResponse(answer=answer)
    except Exception as exc:  # last-resort safety net -- never leak a stack trace
        logger.error(f"Unhandled error in /chat: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Something went wrong while processing your question. Please try again.",
        )


@app.get("/leadership-summary", response_class=PlainTextResponse)
async def leadership_summary() -> str:
    """Generate and return the full Markdown leadership report."""
    monday_service = MondayService()
    fireworks_service = FireworksService()

    try:
        deals_raw = monday_service.fetch_board_items(settings.deals_board_id, "Deals")
        wo_raw = monday_service.fetch_board_items(settings.workorders_board_id, "Work Orders")
    except MondayServiceError as exc:
        logger.error(f"Monday.com integration failure: {exc}")
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        deals_df, deals_quality = clean_deals(deals_raw)
        wo_df, wo_quality = clean_work_orders(wo_raw)
        report = generate_leadership_report_markdown(
            deals_df, wo_df, deals_quality, wo_quality, fireworks_service
        )
        return report
    except Exception as exc:
        logger.error(f"Unhandled error generating leadership summary: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Something went wrong while generating the leadership summary. Please try again.",
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=settings.backend_port, reload=False)
