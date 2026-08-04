"""EDEKA Offers sensor platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    ATTRIBUTION,
    ATTR_DISCOUNTS,
    ATTR_VALID_DATE,
    CONF_MARKET_ID,
    DOMAIN,
)
from .coordinator import EdekaDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: config_entries.ConfigEntry,
    async_add_entities: Any,
) -> None:
    """Set up EDEKA Offers sensor from a config entry."""
    coordinator: EdekaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug(
        "Setting up EDEKA Offers sensors for market %s", coordinator.market_id
    )
    async_add_entities(
        [
            EdekaOffersSensor(coordinator),
            EdekaMarketStatusSensor(coordinator),
        ],
        update_before_add=False,
    )


class EdekaOffersSensor(CoordinatorEntity[EdekaDataUpdateCoordinator], SensorEntity):
    """Represents current EDEKA weekly offers for a given market."""

    _attr_icon = "mdi:cart-percent"
    _attr_native_unit_of_measurement = "items"
    _attr_has_entity_name = True
    _attr_name = "Offers"
    _unrecorded_attributes = frozenset({ATTR_DISCOUNTS})

    def __init__(self, coordinator: EdekaDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._market_id = coordinator.market_id
        self._attr_unique_id = f"edeka_{self._market_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._market_id)},
            name=coordinator.config_entry.title,
            manufacturer="EDEKA",
            model="Market Offers",
            entry_type=None,
            configuration_url=coordinator.configuration_url,
        )
        _LOGGER.debug(
            "Initialized EdekaOffersSensor for market %s (unique_id: %s)",
            self._market_id,
            self._attr_unique_id,
        )

    @property
    def native_value(self) -> int | None:
        """Return the number of current offers."""
        if not self.coordinator.data:
            return None
        discounts = self.coordinator.data.get("discounts", [])
        return len(discounts)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return offer metadata. The full discounts list is excluded from recorder."""
        data = self.coordinator.data or {}
        # Find the earliest valid_until date from offers if not set globally
        valid_until = None
        discounts = data.get("discounts", [])
        if discounts:
            for item in discounts:
                if item.get(ATTR_VALID_DATE):
                    valid_until = item[ATTR_VALID_DATE]
                    break

        return {
            CONF_MARKET_ID: self._market_id,
            ATTR_DISCOUNTS: discounts,
            ATTR_VALID_DATE: valid_until,
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    @property
    def available(self) -> bool:
        """Return True if coordinator has data."""
        return (
            self.coordinator.last_update_success or self.coordinator.is_data_valid
        ) and self.coordinator.data is not None


class EdekaMarketStatusSensor(
    CoordinatorEntity[EdekaDataUpdateCoordinator], SensorEntity
):
    """Represents status (open/closed) and metadata of the local EDEKA market."""

    _attr_icon = "mdi:store"
    _attr_has_entity_name = True
    _attr_name = "Market Status"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: EdekaDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._market_id = coordinator.market_id
        self._attr_unique_id = f"edeka_{self._market_id}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._market_id)},
            name=coordinator.config_entry.title,
            manufacturer="EDEKA",
            model="Market Offers",
            entry_type=None,
            configuration_url=coordinator.configuration_url,
        )
        _LOGGER.debug(
            "Initialized EdekaMarketStatusSensor for market %s (unique_id: %s)",
            self._market_id,
            self._attr_unique_id,
        )

    @property
    def native_value(self) -> str | None:
        """Return the opening status text (e.g. Open / Closed)."""
        if not self.coordinator.data:
            return None
        market_details = self.coordinator.data.get("market_details")
        if not market_details:
            return None
        business_hours = market_details.get("businessHours")
        if not business_hours:
            return None

        import datetime

        now = datetime.datetime.now(datetime.timezone.utc)
        weekday = now.strftime("%A").lower()  # e.g. 'monday'
        day_hours = business_hours.get(weekday)
        if not day_hours or not day_hours.get("open"):
            return "Closed"

        try:
            from_str = day_hours.get("from")
            to_str = day_hours.get("to")
            if from_str and to_str:
                from_time = (
                    datetime.datetime.strptime(from_str, "%H:%M")
                    .replace(tzinfo=datetime.timezone.utc)
                    .time()
                )
                to_time = (
                    datetime.datetime.strptime(to_str, "%H:%M")
                    .replace(tzinfo=datetime.timezone.utc)
                    .time()
                )
                current_time = now.time()
                if from_time <= current_time <= to_time:
                    return "Open"
        except Exception as e:
            _ = e
        return "Closed"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detailed market metadata."""
        if not self.coordinator.data:
            return {ATTR_ATTRIBUTION: ATTRIBUTION}

        market_details = self.coordinator.data.get("market_details") or {}
        coordinates = market_details.get("coordinates") or {}
        address = market_details.get("contact", {}).get("address", {}) or {}
        services = [
            s.get("name")
            for s in market_details.get("services", []) or []
            if s.get("name")
        ]

        # Format opening hours for display
        opening_hours = []
        business_hours = market_details.get("businessHours") or {}
        for day in [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]:
            day_data = business_hours.get(day)
            if day_data:
                status = (
                    f"{day_data.get('from')} - {day_data.get('to')}"
                    if day_data.get("open")
                    else "Geschlossen"
                )
                opening_hours.append(f"{day.capitalize()}: {status}")

        return {
            CONF_MARKET_ID: self._market_id,
            "phone": market_details.get("contact", {}).get("phoneNumber"),
            "street": address.get("street"),
            "zip_code": address.get("city", {}).get("zipCode"),
            "city": address.get("city", {}).get("name"),
            "latitude": coordinates.get("lat"),
            "longitude": coordinates.get("lon"),
            "opening_hours": opening_hours,
            "services": services,
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    @property
    def available(self) -> bool:
        """Return True if coordinator has data."""
        return (
            self.coordinator.last_update_success or self.coordinator.is_data_valid
        ) and self.coordinator.data is not None
