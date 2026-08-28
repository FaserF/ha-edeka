"""Test the EDEKA Offers config flow."""

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.edeka.const import DOMAIN


async def test_config_flow_user_direct_id(hass: HomeAssistant) -> None:
    """Test entering a direct market ID in config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Input direct numeric ID
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"search_or_id": "123456"},
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "EDEKA 123456"
    assert result2["data"] == {"market_id": "123456"}


async def test_config_flow_search_and_select(hass: HomeAssistant) -> None:
    """Test searching for markets and selecting one."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    mock_market = {
        "id": 913988,
        "name": "EDEKA Schlemmer Markt STRUVE",
        "contact": {
            "address": {
                "street": "Bahnhofstr. 31",
                "city": {"name": "Hamburg", "zipCode": "22880"},
            }
        },
        "url": "https://www.edeka.de/eh/nord/e-neukauf-klein-bahnhofstr.-31/index.jsp",
    }

    mock_client = MagicMock()
    mock_client.market_search.return_value = [mock_market]

    with patch(
        "custom_components.edeka.config_flow.EdekaAPIClient", return_value=mock_client
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"search_or_id": "Hamburg"},
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "select_market"

        # Select market
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {"market_id": "913988"},
        )
        assert result3["type"] == FlowResultType.CREATE_ENTRY
        assert result3["title"] == "EDEKA Schlemmer Markt STRUVE (Bahnhofstr. 31)"
        assert result3["data"] == {
            "market_id": "913988",
            "name": "EDEKA Schlemmer Markt STRUVE",
            "street": "Bahnhofstr. 31",
            "city": "Hamburg",
            "zip_code": "22880",
            "url": "https://www.edeka.de/eh/nord/e-neukauf-klein-bahnhofstr.-31/index.jsp",
        }


async def test_options_flow_product_filters(hass: HomeAssistant) -> None:
    """Test options flow with product filters."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.edeka.const import (
        CONF_MARKET_ID,
        CONF_PRODUCT_FILTERS,
        CONF_UPDATE_INTERVAL,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MARKET_ID: "123456"},
        options={CONF_UPDATE_INTERVAL: 24, CONF_PRODUCT_FILTERS: ["Cola"]},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_UPDATE_INTERVAL: 12,
            CONF_PRODUCT_FILTERS: ["Cola", "Pizza"],
            "action": "save",
        },
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["data"][CONF_UPDATE_INTERVAL] == 12
    assert result2["data"][CONF_PRODUCT_FILTERS] == ["Cola", "Pizza"]
