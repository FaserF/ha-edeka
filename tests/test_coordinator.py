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
    mock_client.get_offers.return_value = {"docs": mock_offers, "national": False}
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


async def test_api_html_parsing_and_cached_fallback(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Test HTML offer parsing from /angebote/ and WARNING-only log on valid cache fallback."""
    from datetime import UTC, datetime, timedelta

    from custom_components.edeka.api import EdekaAPIClient

    sample_html = """
    <article data-tracking-event="[&quot;show_promotion&quot;,{&quot;promotion_id&quot;:&quot;16187796&quot;,&quot;promotion_item_name&quot;:&quot;Speisekartoffeln&quot;,&quot;promotion_item_price&quot;:1.99,&quot;promotion_item_category&quot;:&quot;Obst &amp; Gemuese&quot;,&quot;promotion_variant&quot;:&quot;NATIONAL&quot;,&quot;promotion_item_expiration_date&quot;:&quot;2026-11-28T00:00:00Z&quot;}]">
      <a href="#angebot-1" data-tracking-event="[&quot;select_promotion&quot;,{&quot;promotion_id&quot;:&quot;16187796&quot;,&quot;promotion_item_name&quot;:&quot;Speisekartoffeln&quot;,&quot;promotion_item_price&quot;:1.99,&quot;promotion_item_category&quot;:&quot;Obst &amp; Gemuese&quot;,&quot;promotion_variant&quot;:&quot;NATIONAL&quot;,&quot;promotion_item_expiration_date&quot;:&quot;2026-11-28T00:00:00Z&quot;}]">Speisekartoffeln</a>
      <p class="line-clamp-2">Sorte siehe Etikett, 2,5kg</p>
      <img src="https://offer-images.api.edeka/test.png?imwidth=360" />
    </article>
    <dialog id="dialog-angebot-1"><span>Grundpreis: 1kg = € 0,80</span></dialog>
    """
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.content = sample_html.encode()
    fake_resp.text = sample_html
    fake_resp.headers = {"content-type": "text/html; charset=utf-8"}
    fake_resp.cookies = {}
    fake_resp.json.side_effect = ValueError("HTML")

    with patch("custom_components.edeka.api.requests.request", return_value=fake_resp):
        parsed = EdekaAPIClient().get_offers("8001860")

    assert parsed["national"] is True
    assert len(parsed["docs"]) == 1
    assert parsed["docs"][0]["titel"] == "Speisekartoffeln"
    assert parsed["docs"][0]["basicPrice"] == "1kg = € 0,80"
    assert parsed["docs"][0]["gueltig_bis"] == "2026-11-28T00:00:00Z"

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_MARKET_ID: "8001860"}, options={})
    entry.add_to_hass(hass)
    coordinator = EdekaDataUpdateCoordinator(hass, entry)
    coordinator.data = {
        "discounts": [{"product": "Speisekartoffeln"}],
        "valid_until": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
    }
    coordinator._last_success = datetime.now(UTC)

    mock_client = MagicMock()
    mock_client.get_offers.side_effect = RuntimeError("Temporary timeout")
    caplog.clear()
    with (
        patch(
            "custom_components.edeka.coordinator.EdekaAPIClient",
            return_value=mock_client,
        ),
        patch("asyncio.sleep"),
    ):
        fallback = await coordinator._async_update_data()

    assert fallback == coordinator.data
    assert not any(r.levelname == "ERROR" for r in caplog.records)
