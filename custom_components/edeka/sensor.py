"""EDEKA Offers sensor platform."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BASE_PRICE,
    ATTR_CATEGORY,
    ATTR_DISCOUNT_PRICE,
    ATTR_DISCOUNT_TITLE,
    ATTR_DISCOUNTS,
    ATTR_PICTURE,
    ATTR_VALID_DATE,
    ATTRIBUTION,
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
    entities: list[SensorEntity] = [
        EdekaOffersSensor(coordinator),
        EdekaMarketStatusSensor(coordinator),
    ]

    for product_filter in coordinator.product_filters:
        entities.append(EdekaProductFilterSensor(coordinator, product_filter))

    async_add_entities(
        entities,
        update_before_add=False,
    )

    if coordinator.user_token and coordinator.user_token.strip():
        created_account_entities = hass.data[DOMAIN].setdefault(
            "_created_account_entities", set()
        )
        if coordinator.account_key not in created_account_entities:
            created_account_entities.add(coordinator.account_key)
            async_add_entities(
                [
                    EdekaActivatedCouponsSensor(coordinator),
                    EdekaAvailableCouponsSensor(coordinator),
                    EdekaLastReceiptSensor(coordinator),
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

        now = datetime.datetime.now(datetime.UTC)
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
                    .replace(tzinfo=datetime.UTC)
                    .time()
                )
                to_time = (
                    datetime.datetime.strptime(to_str, "%H:%M")
                    .replace(tzinfo=datetime.UTC)
                    .time()
                )
                current_time = now.time()
                if from_time <= current_time <= to_time:
                    return "Open"
        except ValueError, TypeError, AttributeError:
            pass
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

        special_hours = [
            f"{s.get('date')} ({s.get('reason')}): "
            + (f"{s.get('from')} - {s.get('to')}" if s.get("open") else "Geschlossen")
            for s in market_details.get("specialBusinessHours") or []
            if s.get("date")
        ]

        return {
            CONF_MARKET_ID: self._market_id,
            "phone": market_details.get("contact", {}).get("phoneNumber"),
            "street": address.get("street"),
            "zip_code": address.get("city", {}).get("zipCode"),
            "city": address.get("city", {}).get("name"),
            "latitude": coordinates.get("lat"),
            "longitude": coordinates.get("lon"),
            "opening_hours": opening_hours,
            "special_opening_hours": special_hours,
            "services": services,
            "payback_accepted": bool(market_details.get("payback")),
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    @property
    def available(self) -> bool:
        """Return True if coordinator has data."""
        return (
            self.coordinator.last_update_success or self.coordinator.is_data_valid
        ) and self.coordinator.data is not None


class EdekaActivatedCouponsSensor(
    CoordinatorEntity[EdekaDataUpdateCoordinator], SensorEntity
):
    """Represents activated EDEKA App coupons."""

    _attr_icon = "mdi:ticket-confirmation"
    _attr_native_unit_of_measurement = "items"
    _attr_has_entity_name = True
    _attr_name = "Activated Coupons"
    _unrecorded_attributes = frozenset({"coupons"})

    def __init__(self, coordinator: EdekaDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._account_key = coordinator.account_key
        self._attr_unique_id = f"edeka_{self._account_key}_activated_coupons"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._account_key)},
            name="EDEKA Account (DE)",
            manufacturer="EDEKA",
            model="EDEKA Customer Account",
            configuration_url=coordinator.account_configuration_url,
        )

    @property
    def _activated_coupons(self) -> list[dict[str, Any]]:
        if not self.coordinator.data:
            return []
        coupons: list[dict[str, Any]] = self.coordinator.data.get("coupons", [])
        return [c for c in coupons if c.get("activated", False)]

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        return len(self._activated_coupons)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        coupons = self._activated_coupons
        return {
            "coupons": coupons,
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None and bool(self.coordinator.user_token)


class EdekaAvailableCouponsSensor(
    CoordinatorEntity[EdekaDataUpdateCoordinator], SensorEntity
):
    """Represents available (non-activated) EDEKA App coupons."""

    _attr_icon = "mdi:ticket-percent"
    _attr_native_unit_of_measurement = "items"
    _attr_has_entity_name = True
    _attr_name = "Available Coupons"
    _unrecorded_attributes = frozenset({"coupons"})

    def __init__(self, coordinator: EdekaDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._account_key = coordinator.account_key
        self._attr_unique_id = f"edeka_{self._account_key}_available_coupons"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._account_key)},
            name="EDEKA Account (DE)",
            manufacturer="EDEKA",
            model="EDEKA Customer Account",
            configuration_url=coordinator.account_configuration_url,
        )

    @property
    def _available_coupons(self) -> list[dict[str, Any]]:
        if not self.coordinator.data:
            return []
        coupons: list[dict[str, Any]] = self.coordinator.data.get("coupons", [])
        return [c for c in coupons if not c.get("activated", False)]

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        return len(self._available_coupons)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        coupons = self._available_coupons
        return {
            "coupons": coupons,
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None and bool(self.coordinator.user_token)


class EdekaLastReceiptSensor(
    CoordinatorEntity[EdekaDataUpdateCoordinator], SensorEntity
):
    """Represents the last EDEKA purchase receipt."""

    _attr_icon = "mdi:receipt"
    _attr_has_entity_name = True
    _attr_name = "Last Receipt"

    def __init__(self, coordinator: EdekaDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._account_key = coordinator.account_key
        self._attr_unique_id = f"edeka_{self._account_key}_last_receipt"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._account_key)},
            name="EDEKA Account (DE)",
            manufacturer="EDEKA",
            model="EDEKA Customer Account",
            configuration_url=coordinator.account_configuration_url,
        )

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        receipt = self.coordinator.data.get("last_receipt")
        if not receipt:
            return "Keine Kassenbons"
        total = receipt.get("total")
        currency = receipt.get("currency", "EUR")
        return (
            f"{total} {currency}".strip() if total is not None else "Keine Kassenbons"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        receipt = data.get("last_receipt") or {}
        return {
            "date": receipt.get("date"),
            "store": receipt.get("store"),
            "total": receipt.get("total"),
            "currency": receipt.get("currency"),
            "articles_count": receipt.get("articles_count"),
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None and bool(self.coordinator.user_token)


class EdekaProductFilterSensor(
    CoordinatorEntity[EdekaDataUpdateCoordinator], SensorEntity
):
    """Represents a filtered product offer search sensor for an EDEKA market."""

    _attr_icon = "mdi:tag-search"
    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({"matches"})

    def __init__(
        self, coordinator: EdekaDataUpdateCoordinator, product_filter: str
    ) -> None:
        """Initialize the product filter sensor."""
        super().__init__(coordinator)
        self._product_filter = product_filter
        self._market_id = coordinator.market_id
        self._attr_name = product_filter
        self._attr_unique_id = (
            f"edeka_{self._market_id}_filter_{product_filter.lower().replace(' ', '_')}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._market_id)},
            name=coordinator.config_entry.title,
            manufacturer="EDEKA",
            model="Market Offers",
            entry_type=None,
            configuration_url=coordinator.configuration_url,
        )

    def _get_matching_offers(self) -> list[dict[str, Any]]:
        """Calculate matching offers using case-insensitive term matching on product, category, base_price."""
        if not self.coordinator.data:
            return []
        discounts: list[dict[str, Any]] = self.coordinator.data.get("discounts", [])
        term = self._product_filter.lower()
        matches = []
        for offer in discounts:
            product = str(offer.get(ATTR_DISCOUNT_TITLE) or "").lower()
            category = str(offer.get(ATTR_CATEGORY) or "").lower()
            base_price = str(offer.get(ATTR_BASE_PRICE) or "").lower()
            if term in product or term in category or term in base_price:
                matches.append(offer)
        return matches

    def _get_best_offer(self, matches: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Return the offer with the lowest price."""
        if not matches:
            return None

        def _parse_price(item: dict[str, Any]) -> float:
            val = item.get(ATTR_DISCOUNT_PRICE)
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                cleaned = val.replace("€", "").replace(",", ".").strip()
                try:
                    return float(cleaned)
                except ValueError:
                    return float("inf")
            return float("inf")

        return min(matches, key=_parse_price)

    @property
    def native_value(self) -> str:
        """Return the best price found or 'Nicht im Angebot'."""
        matches = self._get_matching_offers()
        best_offer = self._get_best_offer(matches)
        if not best_offer:
            return "Nicht im Angebot"

        price = best_offer.get(ATTR_DISCOUNT_PRICE)
        if price is None:
            return "Nicht im Angebot"

        if isinstance(price, (int, float)):
            return f"{price:.2f} €"

        price_str = str(price).strip()
        if price_str and not price_str.endswith("€"):
            return f"{price_str} €"
        return price_str

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return sensor attributes for the product filter."""
        matches = self._get_matching_offers()
        best_offer = self._get_best_offer(matches)
        best_price = best_offer.get(ATTR_DISCOUNT_PRICE) if best_offer else None

        return {
            "filter": self._product_filter,
            "on_sale": bool(matches),
            "match_count": len(matches),
            "best_price": best_price,
            "base_price": best_offer.get(ATTR_BASE_PRICE) if best_offer else None,
            "product_title": (
                best_offer.get(ATTR_DISCOUNT_TITLE) if best_offer else None
            ),
            "category": best_offer.get(ATTR_CATEGORY) if best_offer else None,
            "valid_until": best_offer.get(ATTR_VALID_DATE) if best_offer else None,
            "picture_link": best_offer.get(ATTR_PICTURE) if best_offer else None,
            "matches": matches,
            ATTR_ATTRIBUTION: ATTRIBUTION,
        }

    @property
    def available(self) -> bool:
        """Return True if coordinator has data."""
        return (
            self.coordinator.last_update_success or self.coordinator.is_data_valid
        ) and self.coordinator.data is not None
