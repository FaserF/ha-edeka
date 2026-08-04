"""Pure Python client for EDEKA Web API using curl_cffi."""

from __future__ import annotations

import logging
from typing import Any, Literal

from curl_cffi import requests

_LOGGER = logging.getLogger(__name__)


class EdekaAPIError(Exception):
    """Exception raised when EDEKA API request fails."""


class EdekaAPIClient:
    """API client that interacts directly with EDEKA web endpoints."""

    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        """Initialize the client with optional cookies."""
        self.cookies: dict[str, str] = cookies or {}

    def _request(
        self,
        method: Literal[
            "GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH", "QUERY"
        ],
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Perform a secure request using curl_cffi."""
        req_headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        if headers:
            req_headers.update(headers)

        # Determine static hardcoded endpoint string to avoid any taint flow to logging
        if "marketsearch/markets" in url:
            log_endpoint = "GET /api/marketsearch/markets"
        elif "service/eh/offers" in url:
            log_endpoint = "GET /eh/service/eh/offers"
        else:
            log_endpoint = "GET /api/unknown"

        log_has_params = "yes" if params else "no"

        _LOGGER.debug(
            "Sending GET request: %s (has_params: %s)", log_endpoint, log_has_params
        )
        try:
            response = requests.request(
                method,
                url,
                params=params,
                headers=req_headers,
                cookies=self.cookies,
                impersonate="chrome",
                timeout=30.0,
            )
            # Update cookies with any new ones returned in the response
            if response.cookies:
                if hasattr(response.cookies, "get_dict"):
                    self.cookies.update(response.cookies.get_dict())
                else:
                    self.cookies.update(dict(response.cookies))
            _LOGGER.debug(
                "Received response for %s: status_code=%s, content_length=%s",
                log_endpoint,
                response.status_code,
                len(response.content) if response.content else 0,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            _LOGGER.error("EDEKA API request failed for %s: %s", log_endpoint, exc)
            raise RuntimeError(f"EDEKA API request failed: {exc}") from exc

    def market_search(self, query: str) -> list[dict[str, Any]]:
        """Search for EDEKA markets using ZIP code, city name, or market name."""
        _LOGGER.debug("Searching for EDEKA market with query: %s", query)
        url = "https://www.edeka.de/api/marketsearch/markets"
        data = self._request("GET", url, params={"limit": 999, "searchstring": query})

        if isinstance(data, dict):
            markets = data.get("markets", [])
            _LOGGER.debug(
                "Market search query '%s' returned %d markets", query, len(markets)
            )
            return markets
        _LOGGER.debug(
            "Market search query '%s' returned empty/invalid response format", query
        )
        return []

    def get_market_by_id(self, market_id: str) -> dict[str, Any] | None:
        """Fetch details for a specific EDEKA market by ID."""
        _LOGGER.debug("Fetching EDEKA market details for ID: %s", market_id)
        url = "https://www.edeka.de/api/marketsearch/markets"
        data = self._request("GET", url, params={"marketId": market_id})
        if isinstance(data, dict):
            markets = data.get("markets", [])
            if markets:
                return markets[0]
        return None

    def get_offers(self, market_id: str) -> list[dict[str, Any]]:
        """Fetch offers for the given market ID."""
        _LOGGER.debug("Fetching offers for EDEKA market_id: %s", market_id)
        url = "https://www.edeka.de/eh/service/eh/offers"
        data = self._request("GET", url, params={"marketId": market_id, "limit": 99999})

        if isinstance(data, dict):
            offers = data.get("docs", [])
            _LOGGER.debug(
                "Offers parsed successfully for market_id %s: %d offers",
                market_id,
                len(offers),
            )
            return offers

        _LOGGER.warning(
            "Offers request for market_id %s did not return a dictionary", market_id
        )
        return []
