"""Test the EDEKA Offers diagnostics."""

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.edeka.const import CONF_MARKET_ID, DOMAIN
from custom_components.edeka.coordinator import EdekaDataUpdateCoordinator
from custom_components.edeka.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics(hass: HomeAssistant) -> None:
    """Test retrieving diagnostic information."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MARKET_ID: "440421"},
        options={"update_interval": 24},
    )
    entry.add_to_hass(hass)

    coordinator = EdekaDataUpdateCoordinator(hass, entry)
    coordinator.data = {
        "discounts": [{"product": "Pringles", "price": "1.49 €"}],
        "valid_until": "2026-07-20",
    }
    hass.data[DOMAIN] = {entry.entry_id: coordinator}

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["entry_id"] == entry.entry_id
    assert diagnostics["entry"]["data"] == {CONF_MARKET_ID: "440421"}
    assert diagnostics["entry"]["options"] == {"update_interval": 24}
    assert diagnostics["coordinator"]["market_id"] == "440421"
    assert diagnostics["coordinator"]["offers_count"] == 1
    assert diagnostics["coordinator"]["has_data"] is True
