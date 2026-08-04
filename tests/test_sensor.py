"""Test the EDEKA Offers sensor platform."""

from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.edeka.const import CONF_MARKET_ID, DOMAIN
from custom_components.edeka.sensor import (
    EdekaMarketStatusSensor,
    EdekaOffersSensor,
    async_setup_entry,
)


def _make_coordinator(hass: HomeAssistant, entry: MockConfigEntry) -> MagicMock:
    coordinator = MagicMock()
    coordinator.market_id = "440421"
    coordinator.config_entry = entry
    coordinator.last_update_success = True
    coordinator.configuration_url = "https://www.edeka.de/marktsuche"
    coordinator.data = {
        "discounts": [{"product": "Pringles", "price": "1.49 €", "category": "Snacks"}],
        "market_details": {
            "coordinates": {"lat": 48.09, "lon": 11.8},
            "contact": {
                "address": {
                    "street": "Birkenstraße 3",
                    "city": {"name": "Zorneding", "zipCode": "85604"},
                },
                "phoneNumber": "+49 123 45678",
            },
            "businessHours": {
                "monday": {
                    "weekday": "MONDAY",
                    "open": True,
                    "from": "07:00",
                    "to": "20:00",
                },
                "tuesday": {
                    "weekday": "TUESDAY",
                    "open": True,
                    "from": "07:00",
                    "to": "20:00",
                },
                "wednesday": {
                    "weekday": "WEDNESDAY",
                    "open": True,
                    "from": "07:00",
                    "to": "20:00",
                },
                "thursday": {
                    "weekday": "THURSDAY",
                    "open": True,
                    "from": "07:00",
                    "to": "20:00",
                },
                "friday": {
                    "weekday": "FRIDAY",
                    "open": True,
                    "from": "07:00",
                    "to": "20:00",
                },
                "saturday": {
                    "weekday": "SATURDAY",
                    "open": True,
                    "from": "07:00",
                    "to": "20:00",
                },
                "sunday": {"weekday": "SUNDAY", "open": False},
            },
            "services": [{"name": "Payback"}, {"name": "WLAN"}],
        },
    }
    return coordinator


async def test_sensor_setup(hass: HomeAssistant) -> None:
    """Test setting up the EDEKA sensor platform."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_MARKET_ID: "440421"}, options={})
    entry.add_to_hass(hass)

    coordinator = _make_coordinator(hass, entry)
    hass.data[DOMAIN] = {entry.entry_id: coordinator}

    async_add_entities = MagicMock()
    await async_setup_entry(hass, entry, async_add_entities)

    assert async_add_entities.called
    entities = async_add_entities.call_args[0][0]
    assert len(entities) == 2
    assert isinstance(entities[0], EdekaOffersSensor)
    assert isinstance(entities[1], EdekaMarketStatusSensor)


async def test_offers_sensor_value_and_attributes(hass: HomeAssistant) -> None:
    """Test value and attributes of EdekaOffersSensor."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_MARKET_ID: "440421"}, options={})
    entry.add_to_hass(hass)

    coordinator = _make_coordinator(hass, entry)
    hass.data[DOMAIN] = {entry.entry_id: coordinator}

    sensor = EdekaOffersSensor(coordinator)
    assert sensor.native_value == 1
    assert len(sensor.extra_state_attributes["discounts"]) == 1
    assert sensor.extra_state_attributes["market_id"] == "440421"


async def test_market_status_sensor_value_and_attributes(hass: HomeAssistant) -> None:
    """Test value and attributes of EdekaMarketStatusSensor."""
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_MARKET_ID: "440421"}, options={})
    entry.add_to_hass(hass)

    coordinator = _make_coordinator(hass, entry)
    hass.data[DOMAIN] = {entry.entry_id: coordinator}

    sensor = EdekaMarketStatusSensor(coordinator)
    # The actual native_value might be "Open" or "Closed" depending on current system time
    val = sensor.native_value
    assert val in ["Open", "Closed"]
    assert sensor.extra_state_attributes["city"] == "Zorneding"
    assert sensor.extra_state_attributes["street"] == "Birkenstraße 3"
    assert sensor.extra_state_attributes["phone"] == "+49 123 45678"
    assert "Payback" in sensor.extra_state_attributes["services"]
    assert "WLAN" in sensor.extra_state_attributes["services"]
