"""EDEKA Offers button platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .coordinator import EdekaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: Any,
) -> None:
    """Set up EDEKA Offers button from a config entry."""
    coordinator: EdekaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug("Setting up EDEKA Offers button for market %s", coordinator.market_id)
    async_add_entities([EdekaForceUpdateButton(coordinator)], update_before_add=False)

    if coordinator.user_token:
        created_buttons = hass.data[DOMAIN].setdefault(
            "_created_account_buttons", set()
        )
        if coordinator.account_key not in created_buttons:
            created_buttons.add(coordinator.account_key)
            async_add_entities(
                [EdekaActivateCouponsButton(coordinator)], update_before_add=False
            )


class EdekaForceUpdateButton(ButtonEntity):
    """Button to force update EDEKA weekly offers."""

    _attr_icon = "mdi:refresh"
    _attr_has_entity_name = True
    _attr_name = "Force Update"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: EdekaDataUpdateCoordinator) -> None:
        """Initialize the button."""
        self.coordinator = coordinator
        self._market_id = coordinator.market_id
        self._attr_unique_id = f"edeka_{self._market_id}_force_update"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._market_id)},
            name=coordinator.config_entry.title,
            manufacturer="EDEKA",
            model="Market Offers",
            entry_type=None,
            configuration_url=coordinator.configuration_url,
        )
        _LOGGER.debug(
            "Initialized EdekaForceUpdateButton for market %s (unique_id: %s)",
            self._market_id,
            self._attr_unique_id,
        )

    async def async_press(self) -> None:
        """Press the button."""
        _LOGGER.info(
            "Forcing EDEKA weekly offers update for market %s", self._market_id
        )
        self.coordinator._force_update = True
        await self.coordinator.async_request_refresh()


class EdekaActivateCouponsButton(ButtonEntity):
    """Button to activate all available EDEKA App coupons."""

    _attr_icon = "mdi:ticket-percent-outline"
    _attr_has_entity_name = True
    _attr_name = "Activate All Coupons"

    def __init__(self, coordinator: EdekaDataUpdateCoordinator) -> None:
        self.coordinator = coordinator
        self._account_key = coordinator.account_key
        self._attr_unique_id = f"edeka_{self._account_key}_activate_coupons"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._account_key)},
            name="EDEKA Account (DE)",
            manufacturer="EDEKA",
            model="EDEKA Customer Account",
            configuration_url=coordinator.account_configuration_url,
        )

    async def async_press(self) -> None:
        _LOGGER.info("Activate all coupons button pressed for EDEKA account")
        await self.coordinator.async_request_refresh()
