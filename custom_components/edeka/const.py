"""Constants for the EDEKA Offers integration."""

DOMAIN = "edeka"
ATTRIBUTION = "Data provided by EDEKA Web API"
PLATFORMS = ["sensor", "button"]

# Configuration keys
CONF_MARKET_ID = "market_id"
CONF_UPDATE_INTERVAL = "update_interval"

# Defaults
DEFAULT_UPDATE_INTERVAL = 24  # hours
MIN_UPDATE_INTERVAL = 1  # hours
MAX_UPDATE_INTERVAL = 24  # hours

# Sensor attributes
ATTR_DISCOUNTS = "discounts"
ATTR_DISCOUNT_TITLE = "product"
ATTR_DISCOUNT_PRICE = "price"
ATTR_BASE_PRICE = "base_price"
ATTR_PICTURE = "picture_link"
ATTR_VALID_DATE = "valid_until"
ATTR_CATEGORY = "category"

# Issue IDs for HA Repairs
ISSUE_ID_CONNECTION = "connection_error"
