"""
Central application configuration.

All secrets and environment-specific values are loaded here from
environment variables. Nothing in this file (or anywhere else) is
ever exposed to the Streamlit frontend directly -- the frontend only
ever talks to the FastAPI backend over HTTP.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load a local .env file if present (no-op in production where the
# platform injects real environment variables).
load_dotenv()


@dataclass(frozen=True)
class Settings:
    monday_api_token: str
    deals_board_id: str
    workorders_board_id: str
    fireworks_api_key: str
    fireworks_model: str
    monday_api_url: str
    backend_port: int
    log_level: str


def get_settings() -> Settings:
    """Build a Settings object from environment variables.

    Missing required variables are NOT raised here -- callers (mainly
    the MondayService and FireworksService) check for empty values and
    return friendly, user-facing errors instead of crashing the app on
    startup. This keeps the API usable for health checks even if a
    single integration is misconfigured.
    """
    return Settings(
        monday_api_token=os.getenv("MONDAY_API_TOKEN", "").strip(),
        deals_board_id=os.getenv("DEALS_BOARD_ID", "").strip(),
        workorders_board_id=os.getenv("WORKORDERS_BOARD_ID", "").strip(),
        fireworks_api_key=os.getenv("FIREWORKS_API_KEY", "").strip(),
        fireworks_model=os.getenv(
            "FIREWORKS_MODEL", "accounts/fireworks/models/llama-v3p1-70b-instruct"
        ).strip(),
        monday_api_url=os.getenv("MONDAY_API_URL", "https://api.monday.com/v2").strip(),
        backend_port=int(os.getenv("PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
    )


settings = get_settings()
