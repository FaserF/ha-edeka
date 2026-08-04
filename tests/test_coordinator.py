"""Test the EDEKA Offers coordinator."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.edeka.const import CONF_MARKET_ID, DOMAIN
from custom_components.edeka.coordinator import EdekaDataUpdateCoordinator

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_coordinator_fetch_success(hass: HomeAssistant) -> None:
    """Test successful data update and storage caching."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MARKET_ID: "440421", "zip_code": "85604"},
        options={},
    )
    entry.add_to_hass(hass)

    coordinator = EdekaDataUpdateCoordinator(hass, entry)

    mock_offers = [
        {
            "angebotid": 500000178,
            "titel": "Mini Rispentomaten",
            "preis": 1.11,
            "beschreibung": "aus den Niederlanden",
            "bild_app": "https://url.png",
            "basicPrice": "1kg = 2,78",
            "warengruppe": "Obst",
            "gueltig_bis": 1784937600000,
        }
    ]

    mock_market = {
        "id": 440421,
        "name": "EDEKA Zorneding",
        "contact": {
            "address": {
                "street": "Birkenstraße 3",
                "city": {"name": "Zorneding", "zipCode": "85604"},
            }
        },
    }

    mock_client = MagicMock()
    mock_client.get_offers.return_value = mock_offers
    mock_client.get_market_by_id.return_value = mock_market
    mock_client.market_search.return_value = [mock_market]
    mock_client.cookies = {}

    with (
        patch(
            "custom_components.edeka.coordinator.EdekaAPIClient",
            return_value=mock_client,
        ),
        patch("homeassistant.helpers.storage.Store.async_save") as mock_save,
        patch("asyncio.sleep"),
    ):
        res = await coordinator._async_update_data()
        assert len(res["discounts"]) == 1
        assert res["discounts"][0]["product"] == "Mini Rispentomaten"
        assert res["market_details"]["name"] == "EDEKA Zorneding"
        mock_save.assert_called_once()


async def test_coordinator_fetch_error(hass: HomeAssistant) -> None:
    """Test handling of API errors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MARKET_ID: "440421"},
        options={},
    )
    entry.add_to_hass(hass)

    coordinator = EdekaDataUpdateCoordinator(hass, entry)

    mock_client = MagicMock()
    mock_client.get_offers.side_effect = RuntimeError("API down")

    with (
        patch(
            "custom_components.edeka.coordinator.EdekaAPIClient",
            return_value=mock_client,
        ),
        patch("asyncio.sleep"),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()
