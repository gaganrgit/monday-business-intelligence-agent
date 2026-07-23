"""
MondayService
=============

Dedicated, read-only client for the monday.com GraphQL API (v2).

This is the ONLY place in the codebase that talks to monday.com.
It never creates, updates, or deletes records -- it only reads
board items and their column values.

The service always fetches fresh data on every call. Local CSV
files are NEVER read once data has been imported into monday.com.
"""

from typing import Any, Dict, List, Optional

import requests

from backend.app.config import settings
from backend.app.logger import get_logger

logger = get_logger(__name__)

MONDAY_TIMEOUT_SECONDS = 20
ITEMS_PAGE_LIMIT = 100


class MondayServiceError(Exception):
    """Raised for any recoverable monday.com integration failure.

    The FastAPI layer catches this and turns it into a friendly,
    user-facing message -- stack traces are never shown to users.
    """


class MondayService:
    """Thin, read-only wrapper around the monday.com GraphQL API."""

    def __init__(self) -> None:
        self.api_url = settings.monday_api_url
        self.api_token = settings.monday_api_token

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.api_token)

    def fetch_board_items(self, board_id: str, board_label: str) -> List[Dict[str, Any]]:
        """Fetch every item (row) on a board, including its column values.

        Returns a list of dicts shaped like:
            {"id": "123", "name": "Acme Corp Deal", "columns": {col_title: text_value, ...}}
        """
        if not self.api_token:
            raise MondayServiceError(
                "Monday.com API token is not configured. "
                "Please set the MONDAY_API_TOKEN environment variable."
            )
        if not board_id:
            raise MondayServiceError(
                f"Board ID for {board_label} is not configured. "
                "Please set the corresponding environment variable."
            )

        logger.info(f"Fetching {board_label} Board...")

        items: List[Dict[str, Any]] = []
        cursor: Optional[str] = None

        try:
            column_titles = self._fetch_column_titles(board_id)

            while True:
                data = self._run_items_page_query(board_id, cursor)
                boards = data.get("boards") or []
                if not boards:
                    raise MondayServiceError(
                        f"Board {board_id} ({board_label}) was not found or is not "
                        "accessible with the provided API token."
                    )

                items_page = boards[0].get("items_page") or {}
                page_items = items_page.get("items") or []

                for raw_item in page_items:
                    items.append(self._parse_item(raw_item, column_titles))

                cursor = items_page.get("cursor")
                if not cursor:
                    break

        except MondayServiceError:
            logger.error(f"API Failure while fetching {board_label} Board")
            raise
        except requests.exceptions.Timeout as exc:
            logger.error(f"Network Timeout while fetching {board_label} Board")
            raise MondayServiceError(
                f"Timed out while contacting monday.com for {board_label}. Please try again."
            ) from exc
        except requests.exceptions.RequestException as exc:
            logger.error(f"API Failure while fetching {board_label} Board: {exc}")
            raise MondayServiceError(
                f"Could not reach monday.com while fetching {board_label}."
            ) from exc

        logger.info(f"Records Retrieved: {len(items)} items from {board_label}")
        logger.info("API Success")
        return items

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": self.api_token,
            "Content-Type": "application/json",
            "API-Version": "2024-10",
        }

    def _execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {"query": query, "variables": variables or {}}
        response = requests.post(
            self.api_url,
            json=payload,
            headers=self._headers(),
            timeout=MONDAY_TIMEOUT_SECONDS,
        )

        if response.status_code == 401:
            raise MondayServiceError(
                "Monday.com rejected the API token (unauthorized). "
                "Please verify MONDAY_API_TOKEN."
            )
        if response.status_code >= 500:
            raise MondayServiceError("Monday.com is currently unavailable. Please try again later.")
        if response.status_code >= 400:
            raise MondayServiceError(
                f"Monday.com API request failed with status {response.status_code}."
            )

        body = response.json()

        if "errors" in body and body["errors"]:
            error_message = "; ".join(
                e.get("message", "Unknown error") for e in body["errors"]
            )
            raise MondayServiceError(f"Monday.com API error: {error_message}")

        return body.get("data", {})

    def _fetch_column_titles(self, board_id: str) -> Dict[str, str]:
        """Map column id -> human-readable column title for a board."""
        query = """
        query ($boardId: [ID!]) {
          boards(ids: $boardId) {
            columns {
              id
              title
            }
          }
        }
        """
        data = self._execute(query, {"boardId": [board_id]})
        boards = data.get("boards") or []
        if not boards:
            raise MondayServiceError(f"Board {board_id} was not found.")
        return {c["id"]: c["title"] for c in boards[0].get("columns", [])}

    def _run_items_page_query(self, board_id: str, cursor: Optional[str]) -> Dict[str, Any]:
        if cursor:
            query = """
            query ($boardId: [ID!], $cursor: String!) {
              boards(ids: $boardId) {
                items_page(limit: %d, cursor: $cursor) {
                  cursor
                  items {
                    id
                    name
                    column_values {
                      id
                      text
                      type
                    }
                  }
                }
              }
            }
            """ % ITEMS_PAGE_LIMIT
            variables = {"boardId": [board_id], "cursor": cursor}
        else:
            query = """
            query ($boardId: [ID!]) {
              boards(ids: $boardId) {
                items_page(limit: %d) {
                  cursor
                  items {
                    id
                    name
                    column_values {
                      id
                      text
                      type
                    }
                  }
                }
              }
            }
            """ % ITEMS_PAGE_LIMIT
            variables = {"boardId": [board_id]}

        return self._execute(query, variables)

    @staticmethod
    def _parse_item(raw_item: Dict[str, Any], column_titles: Dict[str, str]) -> Dict[str, Any]:
        columns: Dict[str, Any] = {}
        for cv in raw_item.get("column_values", []):
            title = column_titles.get(cv["id"], cv["id"])
            columns[title] = cv.get("text")
        return {
            "id": raw_item.get("id"),
            "name": raw_item.get("name"),
            "columns": columns,
        }
