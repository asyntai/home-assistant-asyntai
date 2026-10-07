"""Tests for setting up and removing an Asyntai entry."""

import aiohttp
import pytest

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import ONE_SITE, WEBSITES_URL


async def test_setup_and_unload(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """The entry loads, adds one agent on one service device, and unloads."""
    aioclient_mock.get(WEBSITES_URL, json=ONE_SITE)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    entities = er.async_entries_for_config_entry(
        er.async_get(hass), config_entry.entry_id
    )
    assert [e.entity_id for e in entities] == ["conversation.shop_example"]
    device = dr.async_get(hass).async_get(entities[0].device_id)
    assert device.name == "shop.example"
    assert device.manufacturer == "Asyntai"
    assert device.entry_type is dr.DeviceEntryType.SERVICE

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_bad_key_starts_reauth(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """A refused key at start-up asks the user for a new key."""
    aioclient_mock.get(WEBSITES_URL, status=401, json={"success": False})
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


@pytest.mark.parametrize(
    ("kwargs", "state"),
    [
        ({"exc": aiohttp.ClientConnectionError()}, ConfigEntryState.SETUP_RETRY),
        ({"status": 500, "json": {"success": False}}, ConfigEntryState.SETUP_RETRY),
        ({"status": 403, "json": {"success": False}}, ConfigEntryState.SETUP_ERROR),
        (
            {"json": {"success": True, "websites": [{"id": 1, "domain": "x"}]}},
            ConfigEntryState.SETUP_ERROR,
        ),
    ],
)
async def test_setup_failures(
    hass: HomeAssistant, aioclient_mock, config_entry, kwargs, state
) -> None:
    """Network trouble retries later; a lost plan or website stops."""
    aioclient_mock.get(WEBSITES_URL, **kwargs)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is state
