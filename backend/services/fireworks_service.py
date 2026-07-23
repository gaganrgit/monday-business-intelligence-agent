"""
FireworksService
=================

Thin wrapper around the Fireworks AI chat completions endpoint.

IMPORTANT: this service NEVER receives raw monday.com data. Callers
are responsible for first computing business metrics and passing in
only a small, pre-summarized JSON object.
"""

import json
from typing import Any, Dict, Optional

import requests

from backend.app.config import settings
from backend.app.logger import get_logger

logger = get_logger(__name__)

FIREWORKS_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
FIREWORKS_TIMEOUT_SECONDS = 30

SYSTEM_PROMPT = (
    "You are a Founder Business Intelligence Assistant. "
    "Answer ONLY using the provided analytics. "
    "Do not hallucinate. "
    "Mention assumptions when required. "
    "Mention missing or incomplete data. "
    "Provide concise executive insights. "
    "Give practical recommendations."
)


class FireworksServiceError(Exception):
    """Raised for any recoverable Fireworks AI failure."""


class FireworksService:
    def __init__(self) -> None:
        self.api_key = settings.fireworks_api_key
        self.model = settings.fireworks_model

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate_insight(
        self,
        question: str,
        analytics_summary: Dict[str, Any],
        extra_instructions: Optional[str] = None,
    ) -> str:
        """Send a pre-computed analytics summary + question to Fireworks and
        return the model's natural-language business insight."""
        if not self.api_key:
            raise FireworksServiceError(
                "Fireworks API key is not configured. Please set FIREWORKS_API_KEY."
            )

        user_content = (
            f"Founder's question:\n{question}\n\n"
            f"Business analytics summary (JSON):\n{json.dumps(analytics_summary, default=str)}\n\n"
            + (extra_instructions or "")
        )

        payload = {
            "model": self.model,
            "max_tokens": 900,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.info("Sending Summary to Fireworks...")
        try:
            response = requests.post(
                FIREWORKS_URL, json=payload, headers=headers, timeout=FIREWORKS_TIMEOUT_SECONDS
            )
        except requests.exceptions.Timeout as exc:
            logger.error("Fireworks Error: request timed out")
            raise FireworksServiceError("The AI service timed out. Please try again.") from exc
        except requests.exceptions.RequestException as exc:
            logger.error(f"Fireworks Error: {exc}")
            raise FireworksServiceError("Could not reach the AI service. Please try again.") from exc

        if response.status_code == 401:
            logger.error("Fireworks Error: unauthorized")
            raise FireworksServiceError("Fireworks API key was rejected. Please verify FIREWORKS_API_KEY.")
        if response.status_code >= 400:
            logger.error(f"Fireworks Error: status {response.status_code}")
            raise FireworksServiceError("The AI service returned an error. Please try again.")

        try:
            data = response.json()
            answer = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError) as exc:
            logger.error(f"Fireworks Error: unexpected response shape ({exc})")
            raise FireworksServiceError("Received an unexpected response from the AI service.") from exc

        logger.info("Fireworks Response Received")
        return answer
