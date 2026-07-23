"""
FireworksService
=================

Thin wrapper around the Fireworks AI chat completions endpoint.

IMPORTANT: this service ONLY receives pre-computed, structured evidence
produced by the Business Computation Layer (evidence_builder.py).
It NEVER receives raw monday.com data or unverified analytics dicts.
"""

import json
import re
from typing import Any, Dict, Optional

import requests

from backend.app.config import settings
from backend.app.logger import get_logger

logger = get_logger(__name__)

FIREWORKS_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
FIREWORKS_TIMEOUT_SECONDS = 30

SYSTEM_PROMPT = (
    "You are a Founder Business Intelligence Assistant. "
    "You will receive a structured evidence package produced by a deterministic "
    "Python computation layer. The evidence contains verified facts, warnings, "
    "recommendations, and KPI metrics — all computed without AI involvement.\n\n"
    "STRICT RULES YOU MUST FOLLOW:\n"
    "1. Use ONLY the numbers and facts supplied in the evidence package.\n"
    "2. NEVER invent, estimate, or infer numbers not explicitly present in the evidence.\n"
    "3. NEVER guess missing information. If a metric is unavailable, explicitly state it.\n"
    "4. If the requested metric cannot be calculated from the available evidence, "
    "explain why clearly and concisely.\n"
    "5. Recommendations must be derived ONLY from the computed metrics in evidence — "
    "do not add generic business advice not supported by the data.\n"
    "6. Produce concise founder-level executive summaries — short paragraphs or "
    "bullet points in plain business language.\n"
    "7. Acknowledge any warnings about data quality when they are present in the evidence.\n"
    "8. CRITICAL FORMATTING RULE: Output ONLY the final answer. NEVER show your reasoning, "
    "chain of thought, step-by-step analysis, or how you parsed the JSON. "
    "Do not use phrases like 'We are asked', 'Let's parse', 'I need to', 'Based on the JSON'. "
    "Begin immediately with the insight itself. Keep the response under 250 words unless "
    "the question explicitly requests a detailed report.\n"
    "9. CURRENCY FORMATTING RULE: Always preserve the exact currency symbol provided in the evidence "
    "package (e.g., ₹ for Indian Rupee). NEVER replace '₹' with '€', '$', or any other currency symbol."
)

# Strip reasoning tags that some models emit even when instructed not to.
_REASONING_TAG_PATTERN = re.compile(
    r"<(think|thinking|reasoning|reflection)>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)


def _strip_reasoning_artifacts(text: str) -> str:
    """Remove any chain-of-thought content a model wrapped in reasoning tags."""
    cleaned = _REASONING_TAG_PATTERN.sub("", text)
    return cleaned.strip()


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
        evidence: Dict[str, Any],
        *,
        # Legacy compatibility: analytics_summary accepted but ignored if evidence is provided
        analytics_summary: Optional[Dict[str, Any]] = None,
        extra_instructions: Optional[str] = None,
    ) -> str:
        """
        Send a pre-computed evidence package + question to Fireworks and
        return the model's natural-language founder insight.

        ``evidence`` must be the structured dict produced by evidence_builder.build_evidence().
        The LLM sees ONLY this evidence — never raw DataFrames or analytics dicts.
        """
        logger.info("=================== [FIREWORKS SERVICE] ===================")
        if not self.api_key:
            logger.error("VALIDATION ERROR: Fireworks API key is not configured. Please set FIREWORKS_API_KEY.")
            raise FireworksServiceError(
                "Fireworks API key is not configured. Please set FIREWORKS_API_KEY."
            )

        # If evidence is empty but analytics_summary was passed (e.g., from
        # report_generator.py which has its own evidence path), fall back gracefully.
        payload_data = evidence if evidence else (analytics_summary or {})
        serialized_evidence = json.dumps(payload_data, default=str)

        logger.info(f"Target Model: {self.model}")
        logger.info(
            f"Evidence Payload Size: {len(serialized_evidence)} bytes | "
            f"Facts = {len(payload_data.get('facts', []))}, Warnings = {len(payload_data.get('warnings', []))}, "
            f"Recommendations = {len(payload_data.get('recommendations', []))}"
        )

        user_content = (
            f"Founder's question:\n{question}\n\n"
            f"Evidence package (verified, Python-computed):\n"
            f"{serialized_evidence}\n\n"
        )
        if extra_instructions:
            user_content += extra_instructions

        payload = {
            "model": self.model,
            "max_tokens": 1200,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.info(f"Sending Request to Fireworks API endpoint ({FIREWORKS_URL})")
        try:
            response = requests.post(
                FIREWORKS_URL, json=payload, headers=headers, timeout=FIREWORKS_TIMEOUT_SECONDS
            )
        except requests.exceptions.Timeout as exc:
            logger.error("VALIDATION ERROR: Fireworks request timed out after 30 seconds.")
            raise FireworksServiceError("The AI service timed out. Please try again.") from exc
        except requests.exceptions.RequestException as exc:
            logger.error(f"VALIDATION ERROR: Failed to connect to Fireworks API: {exc}")
            raise FireworksServiceError("Could not reach the AI service. Please try again.") from exc

        if response.status_code == 401:
            logger.error("VALIDATION ERROR: Fireworks API 401 Unauthorized - Key rejected.")
            raise FireworksServiceError("Fireworks API key was rejected. Please verify FIREWORKS_API_KEY.")
        if response.status_code >= 400:
            logger.error(f"VALIDATION ERROR: Fireworks API returned HTTP Status {response.status_code}")
            raise FireworksServiceError("The AI service returned an error. Please try again.")

        try:
            data = response.json()
            message = data["choices"][0]["message"]
            # Some reasoning models return chain-of-thought in "reasoning_content"
            # and the clean answer in "content" -- we only ever use "content".
            answer = (message.get("content") or "").strip()
        except (KeyError, IndexError, ValueError) as exc:
            logger.error(f"VALIDATION ERROR: Unexpected Fireworks API response format ({exc})")
            raise FireworksServiceError("Received an unexpected response from the AI service.") from exc

        answer = _strip_reasoning_artifacts(answer)
        if "€" in answer:
            logger.warning("Post-processing: LLM hallucinated Euro symbol (€). Replacing with Rupee (₹).")
            answer = answer.replace("€", "₹")

        if not answer:
            logger.error("VALIDATION ERROR: Model output was empty after stripping reasoning tags.")
            raise FireworksServiceError("The AI service returned an empty response. Please try again.")

        logger.info(f"Fireworks Insight Received Successfully: Answer Length = {len(answer)} characters")
        return answer
