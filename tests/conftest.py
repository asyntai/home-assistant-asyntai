"""Shared fixtures for the Asyntai tests."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.asyntai.const import (
    CONF_BASE_URL,
    CONF_WEBSITE_DOMAIN,
    CONF_WEBSITE_ID,
    DEFAULT_BASE_URL,
    DOMAIN,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.setup import async_setup_component

API_KEY = "test-key-0123456789"
WEBSITES_URL = f"{DEFAULT_BASE_URL}/api/v1/websites/"
CHAT_URL = f"{DEFAULT_BASE_URL}/api/v1/chat/"

ONE_SITE = {
    "success": True,
    "websites": [{"id": 7, "domain": "shop.example", "is_primary": True}],
}
TWO_SITES = {
    "success": True,
    "websites": [
        {"id": 7, "domain": "shop.example", "is_primary": False},
        {"id": 9, "domain": "help.example", "is_primary": True},
    ],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components in every test."""
    return


@pytest.fixture(autouse=True)
async def core_components(hass, auto_enable_custom_integrations):
    """The conversation component needs the core component, as in a real install."""
    assert await async_setup_component(hass, "homeassistant", {})


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A configured website."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="shop.example",
        unique_id=f"{DEFAULT_BASE_URL}|7",
        data={
            CONF_API_KEY: API_KEY,
            CONF_BASE_URL: DEFAULT_BASE_URL,
            CONF_WEBSITE_ID: 7,
            CONF_WEBSITE_DOMAIN: "shop.example",
        },
    )
