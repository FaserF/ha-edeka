"""Pure Python client for EDEKA Web API using curl_cffi."""

from __future__ import annotations

import html
import json
import logging
import re
import urllib.parse
from typing import Any, Literal

from curl_cffi import requests

_LOGGER = logging.getLogger(__name__)

_OFFER_BLOCK_RE = re.compile(
    r"(<article\b[^>]*>.*?</article>(?:\s*<dialog\b[^>]*>.*?</dialog>)?)",
    re.DOTALL,
)
_TRACKING_EVENT_RE = re.compile(r'data-tracking-event="([^"]+)"')
_IMG_SRC_RE = re.compile(r'<img[^>]+src="(https://offer-images\.api\.edeka/[^"]+)"')
_DESC_RE = re.compile(r'<p class="line-clamp-2">\s*(.*?)\s*</p>', re.DOTALL)
_BASIC_PRICE_RE = re.compile(r"Grundpreis:\s*([^<\n]+)")
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


def _parse_offers_html(html_text: str) -> dict[str, Any]:
    """Parse promotional offer cards from the EDEKA /angebote/ HTML page."""
    docs: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    variants: set[str] = set()

    for block in _OFFER_BLOCK_RE.findall(html_text):
        promo: dict[str, Any] | None = None
        for raw_attr in _TRACKING_EVENT_RE.findall(block):
            try:
                parsed = json.loads(html.unescape(raw_attr))
            except ValueError, TypeError:
                continue
            if (
                isinstance(parsed, list)
                and len(parsed) >= 2
                and parsed[0] in ("select_promotion", "show_promotion")
                and isinstance(parsed[1], dict)
            ):
                promo = parsed[1]
                break

        if not promo:
            continue

        title = str(promo.get("promotion_item_name") or "").strip()
        promo_id = str(promo.get("promotion_id") or "")
        dedup_key = f"{promo_id}:{title}"
        if not title or dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        variant = str(promo.get("promotion_variant") or "")
        if variant:
            variants.add(variant)

        desc_match = _DESC_RE.search(block)
        description = (
            re.sub(
                r"\s+",
                " ",
                _TAG_STRIP_RE.sub(" ", html.unescape(desc_match.group(1))),
            ).strip()
            if desc_match
            else ""
        )
        basic_match = _BASIC_PRICE_RE.search(block)
        basic_price = html.unescape(basic_match.group(1)).strip() if basic_match else ""
        img_match = _IMG_SRC_RE.search(block)
        image_url = html.unescape(img_match.group(1)) if img_match else ""

        docs.append(
            {
                "angebotid": promo_id,
                "titel": title,
                "preis": promo.get("promotion_item_price") or 0.0,
                "beschreibung": description,
                "bild_app": image_url,
                "basicPrice": basic_price,
                "warengruppe": promo.get("promotion_item_category") or "Angebote",
                "gueltig_bis": promo.get("promotion_item_expiration_date") or "",
            }
        )

    is_national = not variants or variants == {"NATIONAL"}
    return {"docs": docs, "national": is_national}


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
        elif "/angebote" in url:
            log_endpoint = "GET /angebote/"
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
            content_type = response.headers.get("content-type", "").lower()
            if "html" in content_type or "/angebote" in url:
                try:
                    return response.json()
                except ValueError:
                    return response.text
            return response.json()
        except Exception as exc:
            _LOGGER.warning("EDEKA API request failed for %s: %s", log_endpoint, exc)
            raise EdekaAPIError(f"EDEKA API request failed: {exc}") from exc

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

    def get_offers(self, market_id: str) -> dict[str, Any]:
        """Fetch offers for the given market ID from the EDEKA web offers page."""
        _LOGGER.debug("Fetching offers for EDEKA market_id: %s", market_id)
        if "EDEKA_B2C" not in self.cookies:
            cookie_payload = json.dumps(
                {"marketID": str(market_id)}, separators=(",", ":")
            )
            self.cookies["EDEKA_B2C"] = urllib.parse.quote(cookie_payload)

        url = "https://www.edeka.de/angebote/"
        data = self._request(
            "GET",
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            },
        )

        if isinstance(data, dict):
            offers = data.get("docs", [])
            _LOGGER.debug(
                "Offers parsed successfully for market_id %s: %d offers (national: %s)",
                market_id,
                len(offers),
                data.get("national"),
            )
            return data

        if isinstance(data, str):
            parsed = _parse_offers_html(data)
            if not parsed["docs"] and "edeka" not in data.lower():
                raise EdekaAPIError(
                    "Unexpected non-EDEKA HTML response from /angebote/"
                )
            _LOGGER.debug(
                "HTML offers parsed successfully for market_id %s: %d offers (national: %s)",
                market_id,
                len(parsed["docs"]),
                parsed["national"],
            )
            return parsed

        _LOGGER.warning(
            "Offers request for market_id %s returned unexpected payload type %s",
            market_id,
            type(data).__name__,
        )
        return {}
