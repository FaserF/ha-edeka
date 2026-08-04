"""Data Update Coordinator for the EDEKA Offers integration.

Anti-ban strategies:
- Random jitter delay (5–30 s) before each request
- Domain-wide asyncio.Lock to serialise concurrent fetches
- Exponential backoff on 403/429 (2 h per failure, max 24 h)
- Restart-resistance: last_success persisted via HA Storage
- Impersonates standard browsers using curl_cffi
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir, storage
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BASE_PRICE,
    ATTR_CATEGORY,
    ATTR_DISCOUNT_PRICE,
    ATTR_DISCOUNT_TITLE,
    ATTR_PICTURE,
    ATTR_VALID_DATE,
    CONF_MARKET_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    ISSUE_ID_CONNECTION,
    MIN_UPDATE_INTERVAL,
)
from .api import EdekaAPIClient

_LOGGER = logging.getLogger(__name__)


class EdekaDataUpdateCoordinator(DataUpdateCoordinator):
    """Manage fetching EDEKA offer data from the Web API."""

    config_entry: config_entries.ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: config_entries.ConfigEntry) -> None:
        config = {**entry.data, **entry.options}
        self.market_id: str = str(config[CONF_MARKET_ID])
        self.config_entry = entry

        # Anti-ban state
        self._backoff_until: datetime | None = None
        self._consecutive_failures: int = 0
        self._last_success: datetime | None = None
        self._issue_created: bool = False
        self._force_update: bool = False

        # HA persistent storage for restart-resistance
        self.store: storage.Store = storage.Store(hass, 1, f"{DOMAIN}_{self.market_id}")

        interval_hours = max(
            MIN_UPDATE_INTERVAL,
            config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        interval_minutes = interval_hours * 60

        _LOGGER.debug(
            "Initializing EDEKA update coordinator for market %s (interval: %d h)",
            self.market_id,
            interval_hours,
        )

        self.configuration_url = (
            entry.data.get("url") or "https://www.edeka.de/marktsuche"
        )
        self.zip_code = entry.data.get("zip_code") or entry.data.get("city") or ""

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"EDEKA {self.market_id}",
            update_interval=timedelta(minutes=interval_minutes),
        )

    @property
    def is_data_valid(self) -> bool:
        """Return True if the current cached data is from the current week and valid."""
        if not self.data or not self._last_success:
            return False

        # If market_details is empty or missing, data is not fully valid
        if not self.data.get("market_details"):
            return False

        now = dt_util.now()
        current_monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return self._last_success >= current_monday

    async def async_load_cache(self) -> None:
        """Load cached data from HA storage (restart-resistance)."""
        _LOGGER.debug(
            "Attempting to load cached EDEKA data for market %s", self.market_id
        )
        cache = await self.store.async_load()
        if cache:
            required_keys = {"discounts"}
            if not required_keys.issubset(cache.keys()):
                _LOGGER.info(
                    "EDEKA cache for market %s is outdated – discarding",
                    self.market_id,
                )
                await self.store.async_remove()
                return

            _LOGGER.debug(
                "Successfully loaded cached EDEKA data for market %s", self.market_id
            )
            self.data = cache
            if "last_success" in cache:
                try:
                    self._last_success = dt_util.parse_datetime(cache["last_success"])
                except (ValueError, TypeError):
                    self._last_success = None
        else:
            _LOGGER.debug("No cached EDEKA data found for market %s", self.market_id)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch new offer data – called by DataUpdateCoordinator on schedule."""
        _LOGGER.debug(
            "Starting EDEKA update cycle for market %s (force_update=%s)",
            self.market_id,
            self._force_update,
        )

        # Backoff guard
        if (
            not self._force_update
            and self._backoff_until
            and dt_util.now() < self._backoff_until
        ):
            _LOGGER.debug(
                "Skipping EDEKA update for market %s – backoff active until %s",
                self.market_id,
                self._backoff_until,
            )
            return self.data

        # Restart-resistance: skip if last fetch was very recent and we have market details
        has_market_details = self.data and self.data.get("market_details")
        if (
            not self._force_update
            and self._last_success is not None
            and has_market_details
        ):
            time_since = dt_util.now() - self._last_success
            effective_interval = self.update_interval or timedelta(
                hours=DEFAULT_UPDATE_INTERVAL
            )
            if time_since < (effective_interval - timedelta(minutes=5)):
                _LOGGER.info(
                    "Skipping EDEKA update for market %s: last success was %d min ago "
                    "(interval %d min)",
                    self.market_id,
                    int(time_since.total_seconds() / 60),
                    int(effective_interval.total_seconds() / 60),
                )
                return self.data

        try:
            domain_data = self.hass.data.setdefault(DOMAIN, {})
            fetch_lock: asyncio.Lock = domain_data.setdefault(
                "fetch_lock", asyncio.Lock()
            )

            _LOGGER.debug(
                "EDEKA market %s: requesting domain-wide fetch lock",
                self.market_id,
            )
            async with fetch_lock:
                _LOGGER.debug(
                    "EDEKA market %s: acquired domain-wide fetch lock",
                    self.market_id,
                )
                is_first_fetch = self._last_success is None
                if not self._force_update and not is_first_fetch:
                    jitter = random.uniform(5.0, 30.0)
                    _LOGGER.debug(
                        "EDEKA market %s: waiting %.1f s jitter before fetch to prevent rate limits",
                        self.market_id,
                        jitter,
                    )
                    await asyncio.sleep(jitter)
                elif is_first_fetch:
                    _LOGGER.debug(
                        "EDEKA market %s: first fetch – skipping jitter",
                        self.market_id,
                    )
                else:
                    _LOGGER.info(
                        "EDEKA market %s: forced update, skipping jitter",
                        self.market_id,
                    )
                    self._force_update = False

                _LOGGER.debug(
                    "EDEKA market %s: initiating API call via executor job",
                    self.market_id,
                )
                async with asyncio.timeout(90):
                    existing_cookies = self.config_entry.data.get("cookies", {})
                    data, new_cookies = await self.hass.async_add_executor_job(
                        self._fetch_offers_sync, existing_cookies
                    )

            _LOGGER.debug(
                "EDEKA market %s: fetch completed, updating success metadata",
                self.market_id,
            )
            self._last_success = dt_util.now()
            self._consecutive_failures = 0
            data["last_success"] = self._last_success.isoformat()
            await self.store.async_save(data)

            # Update config entry with cached details and cookies if needed
            updated_data = {**self.config_entry.data}
            updated = False

            market_details = data.get("market_details")
            if market_details and self.config_entry:
                addr = market_details.get("contact", {}).get("address", {})
                new_zip = addr.get("city", {}).get("zipCode") or ""
                new_city = addr.get("city", {}).get("name") or ""
                new_street = addr.get("street") or ""
                new_url = market_details.get("url") or ""

                if new_zip and not self.config_entry.data.get("zip_code"):
                    updated_data["zip_code"] = new_zip
                    self.zip_code = new_zip
                    updated = True
                if new_city and not self.config_entry.data.get("city"):
                    updated_data["city"] = new_city
                    updated = True
                if new_street and not self.config_entry.data.get("street"):
                    updated_data["street"] = new_street
                    updated = True
                if new_url and not self.config_entry.data.get("url"):
                    updated_data["url"] = new_url
                    updated = True

            if new_cookies != existing_cookies:
                _LOGGER.debug(
                    "EDEKA market %s: updating session cookies in config entry",
                    self.market_id,
                )
                updated_data["cookies"] = new_cookies
                updated = True

            if updated:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=updated_data,
                )

            # Clear any active repair issue
            if self._issue_created:
                _LOGGER.debug(
                    "EDEKA market %s: clearing active connection repair issue",
                    self.market_id,
                )
                ir.async_delete_issue(self.hass, DOMAIN, ISSUE_ID_CONNECTION)
                self._issue_created = False

            return data

        except Exception as err:
            self._consecutive_failures += 1
            _LOGGER.warning(
                "EDEKA market %s: fetch attempt failed (consecutive failures: %d). Error: %s",
                self.market_id,
                self._consecutive_failures,
                err,
            )

            # Raise a HA Repair issue if we haven't succeeded in 24 h
            # Raise a HA Repair issue if we haven't succeeded in 24 h
            if (
                self._last_success
                and (dt_util.now() - self._last_success) > timedelta(hours=24)
                and not self._issue_created
            ):
                _LOGGER.warning(
                    "EDEKA market %s: creating connection repair issue as no updates succeeded in 24 hours",
                    self.market_id,
                )
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    ISSUE_ID_CONNECTION,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="connection_error",
                )
                self._issue_created = True

            # Exponential backoff on rate-limit / blocked responses
            status = getattr(err, "status", None)
            err_str = str(err).lower()
            if status in (403, 429) or "403" in err_str or "429" in err_str:
                backoff_hours = min(24, self._consecutive_failures * 2)
                self._backoff_until = dt_util.now() + timedelta(hours=backoff_hours)
                _LOGGER.error(
                    "EDEKA market %s: rate-limited / blocked. Backing off %d h.",
                    self.market_id,
                    backoff_hours,
                )
            else:
                backoff_minutes = min(240, self._consecutive_failures * 30)
                self._backoff_until = dt_util.now() + timedelta(minutes=backoff_minutes)
                _LOGGER.error(
                    "EDEKA market %s: fetch error (failure #%d). Backing off %d min. "
                    "Error: %s",
                    self.market_id,
                    self._consecutive_failures,
                    backoff_minutes,
                    err,
                )

            raise UpdateFailed(
                f"Error fetching EDEKA offers for market {self.market_id}: {err}"
            ) from err

    def _fetch_offers_sync(
        self, cookies: dict[str, str]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Fetch and parse EDEKA offers using EdekaAPIClient."""
        _LOGGER.debug(
            "EDEKA market %s: starting synchronous fetch sequence", self.market_id
        )
        try:
            client = EdekaAPIClient(cookies=cookies)
            raw_offers = client.get_offers(self.market_id)

            parsed_discounts = []
            for offer in raw_offers:
                # Convert milliseconds timestamp to ISO format string
                valid_date_str = ""
                if offer.get("gueltig_bis"):
                    try:
                        valid_date_str = datetime.fromtimestamp(
                            offer["gueltig_bis"] / 1000.0, tz=timezone.utc
                        ).isoformat()
                    except Exception as e:
                        _ = e

                parsed_discounts.append(
                    {
                        ATTR_DISCOUNT_TITLE: offer.get("titel") or "",
                        ATTR_DISCOUNT_PRICE: offer.get("preis") or 0.0,
                        ATTR_BASE_PRICE: offer.get("basicPrice") or "",
                        ATTR_PICTURE: offer.get("bild_app") or "",
                        ATTR_VALID_DATE: valid_date_str,
                        ATTR_CATEGORY: offer.get("warengruppe") or "Angebote",
                    }
                )

            # Query latest market details (opening hours, services) using fallback search terms
            search_queries = []
            if self.zip_code:
                search_queries.append(self.zip_code)

            # Access entry data safely
            entry_data = (
                getattr(self.config_entry, "data", {})
                if hasattr(self, "config_entry")
                else {}
            )
            street = entry_data.get("street")
            if street:
                search_queries.append(street)
            city = entry_data.get("city")
            if city:
                search_queries.append(city)

            # Try config entry title parsing as last resort fallback
            title = (
                getattr(self.config_entry, "title", "")
                if hasattr(self, "config_entry")
                else ""
            )
            if "(" in title and ")" in title:
                extracted = title.split("(")[1].split(")")[0]
                if extracted:
                    search_queries.append(extracted)
            elif title.startswith("EDEKA "):
                search_queries.append(title[6:])

            # Make search queries unique
            seen = set()
            unique_queries = []
            for x in search_queries:
                if x and x not in seen:
                    seen.add(x)
                    unique_queries.append(x)
            search_queries = unique_queries

            market_details = {}
            try:
                market_details = client.get_market_by_id(self.market_id) or {}
            except Exception as e:
                _LOGGER.warning(
                    "Could not fetch market details directly by ID %s: %s",
                    self.market_id,
                    e,
                )

            if not market_details:
                for query in search_queries:
                    try:
                        markets = client.market_search(query)
                        for m in markets:
                            if str(m.get("id")) == self.market_id:
                                market_details = m
                                break
                        if market_details:
                            break
                    except Exception as e:
                        _LOGGER.warning(
                            "Could not fetch market details for %s with query %s: %s",
                            self.market_id,
                            query,
                            e,
                        )

            data = {
                "discounts": parsed_discounts,
                "market_details": market_details,
            }
            return data, client.cookies
        except Exception as exc:
            _LOGGER.error("EDEKA sync fetch failed: %s", exc)
            raise

    @callback
    def force_update(self) -> None:
        """Trigger an immediate update bypass scheduled checks and backoffs."""
        _LOGGER.info("Forcing immediate update for EDEKA market %s", self.market_id)
        self._force_update = True
        self._backoff_until = None
