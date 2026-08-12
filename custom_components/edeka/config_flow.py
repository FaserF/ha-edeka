"""Config flow for EDEKA Offers integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .api import EdekaAPIClient
from .const import (
    CONF_AUTO_ACTIVATE_COUPONS,
    CONF_CARD_NUMBER,
    CONF_MARKET_ID,
    CONF_REFRESH_TOKEN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class EdekaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EDEKA Offers."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._search_results: list[dict[str, Any]] = []
        self._discovery_data: dict[str, Any] = {}
        self._login_requested: bool = False
        self._selected_entry_data: dict[str, Any] = {}
        self._selected_title: str = ""

    async def async_step_login(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle account token / card number configuration step."""
        if user_input is not None:
            self._selected_entry_data[CONF_CARD_NUMBER] = user_input.get(
                CONF_CARD_NUMBER, ""
            )
            self._selected_entry_data[CONF_REFRESH_TOKEN] = user_input.get(
                CONF_REFRESH_TOKEN, ""
            )
            self._selected_entry_data[CONF_AUTO_ACTIVATE_COUPONS] = user_input.get(
                CONF_AUTO_ACTIVATE_COUPONS, False
            )
            return self.async_create_entry(
                title=self._selected_title,
                data=self._selected_entry_data,
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_CARD_NUMBER, default=""): str,
                vol.Optional(CONF_REFRESH_TOKEN, default=""): str,
                vol.Optional(CONF_AUTO_ACTIVATE_COUPONS, default=False): bool,
            }
        )
        return self.async_show_form(step_id="login", data_schema=schema)

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
            self._login_requested = bool(
                user_input.get("login_to_edeka_account", False)
            )

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

            except Exception as exc:  # noqa: BLE001
                _LOGGER.error("EDEKA market search error: %s", exc)
                errors["base"] = "search_failed"

        # Show input form for search queries or direct IDs
        schema = vol.Schema(
            {
                vol.Required("search_or_id"): str,
                vol.Optional("login_to_edeka_account", default=False): bool,
            }
        )
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

            if self._login_requested:
                self._selected_entry_data = entry_data
                self._selected_title = selected_name
                return await self.async_step_login()

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
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            action = user_input.get("action", "save")
            if action == "login":
                return await self.async_step_login()
            if action == "logout":
                new_data = {
                    k: v
                    for k, v in self._config_entry.data.items()
                    if k not in (CONF_REFRESH_TOKEN, CONF_CARD_NUMBER)
                }
                new_options = {
                    k: v
                    for k, v in self._config_entry.options.items()
                    if k not in (CONF_REFRESH_TOKEN, CONF_CARD_NUMBER)
                }
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data, options=new_options
                )
                return self.async_create_entry(title="", data=new_options)

            return self.async_create_entry(
                title="",
                data={
                    CONF_UPDATE_INTERVAL: int(user_input[CONF_UPDATE_INTERVAL]),
                    CONF_CARD_NUMBER: str(user_input.get(CONF_CARD_NUMBER, "")).strip(),
                    CONF_REFRESH_TOKEN: str(
                        user_input.get(CONF_REFRESH_TOKEN, "")
                    ).strip(),
                    CONF_AUTO_ACTIVATE_COUPONS: bool(
                        user_input.get(CONF_AUTO_ACTIVATE_COUPONS, False)
                    ),
                },
            )

        current_interval = self._config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        current_card_number = self._config_entry.options.get(CONF_CARD_NUMBER, "")
        current_user_token = self._config_entry.options.get(
            CONF_REFRESH_TOKEN, self._config_entry.data.get(CONF_REFRESH_TOKEN, "")
        )
        current_auto_activate = self._config_entry.options.get(
            CONF_AUTO_ACTIVATE_COUPONS, False
        )
        is_logged_in = bool(current_user_token or current_card_number)

        action_choices: dict[str, str] = {"save": "Save settings"}
        if is_logged_in:
            action_choices["login"] = "Update Account / Loyalty Card"
            action_choices["logout"] = "Log out / Remove Account Data"
        else:
            action_choices["login"] = "Configure EDEKA / PAYBACK Account"

        schema_dict: dict[Any, Any] = {
            vol.Optional(
                CONF_UPDATE_INTERVAL, default=current_interval
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_UPDATE_INTERVAL,
                    max=MAX_UPDATE_INTERVAL,
                    step=1,
                    unit_of_measurement="hours",
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }

        if is_logged_in:
            schema_dict[vol.Optional(CONF_CARD_NUMBER, default=current_card_number)] = (
                str
            )
            schema_dict[vol.Optional(CONF_REFRESH_TOKEN, default=current_user_token)] = (
                str
            )
            schema_dict[
                vol.Optional(CONF_AUTO_ACTIVATE_COUPONS, default=current_auto_activate)
            ] = bool

        schema_dict[vol.Required("action", default="save")] = vol.In(action_choices)

        options_schema = vol.Schema(schema_dict)
        return self.async_show_form(step_id="init", data_schema=options_schema)

    async def async_step_login(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle account token / card number configuration in options."""
        if user_input is not None:
            new_options = {**self._config_entry.options, **user_input}
            return self.async_create_entry(title="", data=new_options)

        current_card_number = self._config_entry.options.get(CONF_CARD_NUMBER, "")
        current_user_token = self._config_entry.options.get(
            CONF_REFRESH_TOKEN, self._config_entry.data.get(CONF_REFRESH_TOKEN, "")
        )
        current_auto_activate = self._config_entry.options.get(
            CONF_AUTO_ACTIVATE_COUPONS, False
        )

        schema = vol.Schema(
            {
                vol.Optional(CONF_CARD_NUMBER, default=current_card_number): str,
                vol.Optional(CONF_REFRESH_TOKEN, default=current_user_token): str,
                vol.Optional(
                    CONF_AUTO_ACTIVATE_COUPONS, default=current_auto_activate
                ): bool,
            }
        )
        return self.async_show_form(step_id="login", data_schema=schema)
