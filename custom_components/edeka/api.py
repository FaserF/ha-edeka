"""Pure Python client for official EDEKA JSON & Mobile B2C APIs using curl_cffi."""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

from curl_cffi import requests

_LOGGER = logging.getLogger(__name__)

_TOKEN_URL = "https://b2b-login.api.edeka/auth/realms/b2b/protocol/openid-connect/token"
_MOBILE_OFFERS_URL = "https://b2c-gw.api.edeka/v2/offers/mobile"
_B2C_MARKETS_URL = "https://b2c-gw.api.edeka/v4/markets"
_MARKET_SEARCH_URL = "https://www.edeka.de/api/marketsearch/markets"

# Public anonymous mobile app OAuth2 client embedded in the official EDEKA Android APK
_MOBILE_APP_CLIENT_ID = "edeka-app-android-client"
_MOBILE_APP_CLIENT_CRED = "wFoBG7VhAIn48kx9SDyVhaN9FttvPZi2"


def _normalize_mobile_offer(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert an official /v2/offers/mobile JSON object to internal offer keys."""
    price_obj = raw.get("price") if isinstance(raw.get("price"), dict) else {}
    raw_val = price_obj.get("rawValue")
    price_num = 0.0
    if isinstance(raw_val, (int, float)):
        price_num = float(raw_val)
    elif price_obj.get("value") is not None:
        try:
            price_num = float(str(price_obj["value"]).replace(",", "."))
        except ValueError:
            price_num = 0.0

    descriptions = [
        str(d).strip() for d in (raw.get("descriptions") or []) if d and str(d).strip()
    ]
    image_obj = raw.get("image") if isinstance(raw.get("image"), dict) else {}
    cat_obj = raw.get("category") if isinstance(raw.get("category"), dict) else {}
    criteria = raw.get("criteria") if isinstance(raw.get("criteria"), list) else []
    first_crit = (
        criteria[0].get("name") if criteria and isinstance(criteria[0], dict) else None
    )

    return {
        "angebotid": raw.get("id"),
        "titel": str(raw.get("title") or "").strip(),
        "preis": price_num,
        "beschreibung": ", ".join(descriptions),
        "bild_app": str(image_obj.get("imageUrl") or ""),
        "basicPrice": str(raw.get("priceLabel") or raw.get("discount") or ""),
        "warengruppe": str(cat_obj.get("name") or first_crit or "Angebote"),
        "gueltig_bis": str(raw.get("validTill") or ""),
    }


class EdekaAPIError(Exception):
    """Exception raised when EDEKA API request fails."""


class EdekaAPIClient:
    """API client interacting strictly with official EDEKA JSON REST APIs."""

    def __init__(
        self,
        cookies: dict[str, str] | None = None,
        client_id: str = _MOBILE_APP_CLIENT_ID,
        client_cred: str = _MOBILE_APP_CLIENT_CRED,
    ) -> None:
        """Initialize the client with optional cookies and OAuth client info."""
        self.cookies: dict[str, str] = cookies or {}
        self._client_id = client_id
        self._client_cred = client_cred
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def _request(
        self,
        method: Literal[
            "GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH", "QUERY"
        ],
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
    ) -> Any:
        """Perform an HTTPS JSON request using curl_cffi."""
        req_headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": "okhttp/5.3.2",
        }
        if headers:
            req_headers.update(headers)

        # Static endpoint string avoids taint flow into debug logs
        if "marketsearch/markets" in url:
            log_endpoint = "GET /api/marketsearch/markets"
        elif "v2/offers/mobile" in url:
            log_endpoint = "GET /v2/offers/mobile"
        elif "v4/markets" in url:
            log_endpoint = "GET /v4/markets"
        elif "openid-connect/token" in url:
            log_endpoint = "POST /protocol/openid-connect/token"
        else:
            log_endpoint = "GET /api/unknown"

        log_has_params = "yes" if params else "no"

        _LOGGER.debug(
            "Sending %s request: %s (has_params: %s)",
            method,
            log_endpoint,
            log_has_params,
        )
        try:
            response = requests.request(
                method,
                url,
                params=params,
                data=data,
                headers=req_headers,
                cookies=self.cookies,
                impersonate="chrome",
                timeout=30.0,
            )
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
            _LOGGER.warning("EDEKA API request failed for %s: %s", log_endpoint, exc)
            raise EdekaAPIError(f"EDEKA API request failed: {exc}") from exc

    def _ensure_offers_token(self) -> str:
        """Obtain and cache a short-lived anonymous mobile OAuth2 bearer token."""
        if self._access_token and time.monotonic() < self._token_expires_at:
            return self._access_token

        payload = self._request(
            "POST",
            _TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_cred,
            },
        )
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise EdekaAPIError("Failed to obtain EDEKA OAuth2 access token")

        self._access_token = str(payload["access_token"])
        expires_in = max(60, int(payload.get("expires_in") or 300))
        self._token_expires_at = time.monotonic() + max(30, expires_in - 60)
        return self._access_token

    def market_search(self, query: str) -> list[dict[str, Any]]:
        """Search for EDEKA markets using ZIP code, city name, or market name."""
        _LOGGER.debug("Searching for EDEKA market with query: %s", query)
        data = self._request(
            "GET", _MARKET_SEARCH_URL, params={"limit": 999, "searchstring": query}
        )

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
        data = self._request("GET", _MARKET_SEARCH_URL, params={"marketId": market_id})
        if isinstance(data, dict):
            markets = data.get("markets", [])
            if markets:
                return markets[0]
        return None

    def _get_market_gln(self, market_id: str, token: str) -> str | None:
        """Resolve a market's GLN via the official B2C v4/markets API."""
        data = self._request(
            "GET",
            f"{_B2C_MARKETS_URL}/{market_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if isinstance(data, dict):
            core = data.get("coreData")
            if isinstance(core, dict) and core.get("gln"):
                return str(core["gln"])
        return None

    def get_offers(self, market_id: str) -> dict[str, Any]:
        """Fetch paginated offers from the official /v2/offers/mobile JSON API."""
        _LOGGER.debug("Fetching offers for EDEKA market_id: %s", market_id)
        token = self._ensure_offers_token()
        auth_headers = {"Authorization": f"Bearer {token}"}

        docs: list[dict[str, Any]] = []
        is_national = False
        query_key = "marketId"
        query_val = str(market_id)

        for page in range(20):
            try:
                data = self._request(
                    "GET",
                    _MOBILE_OFFERS_URL,
                    params={
                        query_key: query_val,
                        "size": 200,
                        "page": page,
                        "sortedByCategory": "true",
                    },
                    headers=auth_headers,
                )
            except EdekaAPIError:
                if page == 0 and query_key == "marketId":
                    gln = self._get_market_gln(market_id, token)
                    if gln:
                        query_key = "marketGln"
                        query_val = gln
                        data = self._request(
                            "GET",
                            _MOBILE_OFFERS_URL,
                            params={
                                query_key: query_val,
                                "size": 200,
                                "page": 0,
                                "sortedByCategory": "true",
                            },
                            headers=auth_headers,
                        )
                    else:
                        raise
                else:
                    raise

            if not isinstance(data, dict):
                break
            if "docs" in data and isinstance(data["docs"], list):
                return data
            if page == 0:
                is_national = bool(data.get("national", False))

            raw_offers = data.get("offers") or []
            if not isinstance(raw_offers, list) or not raw_offers:
                break
            docs.extend(
                _normalize_mobile_offer(item)
                for item in raw_offers
                if isinstance(item, dict)
            )
            total_count = data.get("totalCount")
            if isinstance(total_count, int) and len(docs) >= total_count:
                break
            if len(raw_offers) < 200:
                break

        _LOGGER.debug(
            "Offers fetched for market_id %s: %d offers (national: %s)",
            market_id,
            len(docs),
            is_national,
        )
        return {"docs": docs, "national": is_national}
