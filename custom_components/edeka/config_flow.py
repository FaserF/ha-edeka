"""Config flow for EDEKA Offers integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .api import EdekaAPIClient, EdekaAPIError
from .const import (
    CONF_MARKET_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class EdekaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for EDEKA Offers."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._search_results: list[dict[str, Any]] = []
        self._discovery_data: dict[str, Any] = {}

    async def async_step_integration_discovery(
        self, discovery_info: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Handle a discovered EDEKA market (triggered by location-based auto-discovery)."""
        market_id = str(discovery_info.get(CONF_MARKET_ID, "")).strip()
        if not market_id:
            return self.async_abort(reason="no_markets_found")

        await self.async_set_unique_id(market_id)
        self._abort_if_unique_id_configured()

        self._discovery_data = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.get("name", "EDEKA Markt"),
            "city": discovery_info.get("city", ""),
            "street": discovery_info.get("street", ""),
        }
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm adding the discovered market."""
        if user_input is not None:
            name = self._discovery_data.get("name", "EDEKA Markt")
            street = self._discovery_data.get("street", "")
            if name.lower().startswith("edeka"):
                title = f"{name} ({street})" if street else name
            else:
                title = f"EDEKA {name} ({street})" if street else f"EDEKA {name}"
            return self.async_create_entry(title=title, data=self._discovery_data)

        return self.async_show_form(step_id="discovery_confirm")

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial user input step."""
        _LOGGER.debug("async_step_user called with input: %s", user_input)
        errors: dict[str, str] = {}

        if user_input is not None:
            user_value = user_input["search_or_id"].strip()

            # Direct numeric ID check
            if user_value.isdigit() and len(user_value) >= 5:
                _LOGGER.debug("Direct market ID detected: %s", user_value)
                await self.async_set_unique_id(user_value)
                self._abort_if_unique_id_configured()
                _LOGGER.debug(
                    "Creating config entry directly for market ID: %s", user_value
                )
                return self.async_create_entry(
                    title=f"EDEKA {user_value}",
                    data={CONF_MARKET_ID: user_value},
                )

            # Search text path
            try:
                _LOGGER.debug("Executing market search for query: '%s'", user_value)
                client = EdekaAPIClient()
                results = await self.hass.async_add_executor_job(
                    client.market_search, user_value
                )

                if not results:
                    _LOGGER.info("No markets found matching query '%s'", user_value)
                    errors["base"] = "no_markets_found"
                else:
                    _LOGGER.debug(
                        "Found %d markets matching query '%s'", len(results), user_value
                    )
                    self._search_results = results
                    return await self.async_step_select_market()

            except (EdekaAPIError, TimeoutError, OSError) as exc:
                _LOGGER.error("EDEKA market search error: %s", exc)
                errors["base"] = "search_failed"

        # Show input form for search queries or direct IDs
        schema = vol.Schema({vol.Required("search_or_id"): str})
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_select_market(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle selecting a market from search results."""
        _LOGGER.debug("async_step_select_market called with input: %s", user_input)
        errors: dict[str, str] = {}

        if user_input is not None:
            market_id = str(user_input[CONF_MARKET_ID])
            await self.async_set_unique_id(market_id)
            self._abort_if_unique_id_configured()

            selected_name = f"EDEKA {market_id}"
            entry_data = {CONF_MARKET_ID: market_id}
            for res in self._search_results:
                if str(res.get("id")) == market_id:
                    addr = res.get("contact", {}).get("address", {})
                    street = addr.get("street") or ""
                    city = addr.get("city", {}).get("name") or ""
                    name = res.get("name") or "EDEKA Markt"
                    if name.lower().startswith("edeka"):
                        selected_name = f"{name} ({street})"
                    else:
                        selected_name = f"EDEKA {name} ({street})"
                    entry_data["name"] = name
                    entry_data["street"] = street
                    entry_data["city"] = city
                    entry_data["zip_code"] = addr.get("city", {}).get("zipCode") or ""
                    entry_data["url"] = res.get("url") or ""
                    break

            _LOGGER.info(
                "Creating config entry for market: %s (ID: %s)",
                selected_name,
                market_id,
            )
            return self.async_create_entry(
                title=selected_name,
                data=entry_data,
            )

        # Build dropdown options
        options: dict[str, str] = {}
        for res in self._search_results:
            market_id = str(res.get("id", ""))
            if market_id:
                name = res.get("name", "EDEKA Markt")
                addr = res.get("contact", {}).get("address", {})
                street = addr.get("street") or ""
                city = addr.get("city", {}).get("name") or ""
                options[market_id] = f"{name}, {street}, {city} (ID: {market_id})"

        if not options:
            return self.async_abort(reason="no_markets_found")

        schema = vol.Schema({vol.Required(CONF_MARKET_ID): vol.In(options)})
        return self.async_show_form(
            step_id="select_market",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> EdekaOptionsFlowHandler:
        """Return the options flow handler."""
        return EdekaOptionsFlowHandler(config_entry)


class EdekaOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for EDEKA Offers."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__()
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        _LOGGER.debug(
            "EdekaOptionsFlowHandler async_step_init called with input: %s", user_input
        )
        if user_input is not None:
            _LOGGER.info(
                "Updating options for EDEKA entry %s: %s",
                self.config_entry.entry_id,
                user_input,
            )
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )

        options_schema = vol.Schema(
            {
                vol.Optional(CONF_UPDATE_INTERVAL, default=current_interval): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=options_schema)
