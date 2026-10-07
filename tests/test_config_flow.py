"""Tests for the Asyntai config flow."""

from unittest.mock import patch

import aiohttp
import pytest

from custom_components.asyntai.const import (
    CONF_BASE_URL,
    CONF_WEBSITE_DOMAIN,
    CONF_WEBSITE_ID,
    DEFAULT_BASE_URL,
    DOMAIN,
)
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import API_KEY, ONE_SITE, TWO_SITES, WEBSITES_URL


@pytest.fixture(autouse=True)
def no_setup():
    """Do not start the entry: these tests are about the flow only."""
    with patch("custom_components.asyntai.async_setup_entry", return_value=True):
        yield


async def _start(hass: HomeAssistant):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_one_website_creates_entry(hass: HomeAssistant, aioclient_mock) -> None:
    """One website on the account: the entry is made at once."""
    aioclient_mock.get(WEBSITES_URL, json=ONE_SITE)
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert list(result["data_schema"].schema) == [CONF_API_KEY]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: f"  {API_KEY} "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "shop.example"
    assert result["data"] == {
        CONF_API_KEY: API_KEY,
        CONF_BASE_URL: DEFAULT_BASE_URL,
        CONF_WEBSITE_ID: 7,
        CONF_WEBSITE_DOMAIN: "shop.example",
    }
    assert result["result"].unique_id == f"{DEFAULT_BASE_URL}|7"
    # The key goes in the Authorization header, never in the URL.
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Bearer {API_KEY}"


async def test_two_websites_asks_which(hass: HomeAssistant, aioclient_mock) -> None:
    """Several websites: the user picks one, the primary is preselected."""
    aioclient_mock.get(WEBSITES_URL, json=TWO_SITES)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "website"
    schema = result["data_schema"].schema
    key = next(iter(schema))
    assert key.default() == "9"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WEBSITE_ID: "7"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "shop.example"
    assert result["data"][CONF_WEBSITE_ID] == 7


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (401, {"success": False, "error": "Invalid API key"}, "invalid_auth"),
        (403, {"success": False, "error": "paid plan"}, "plan_required"),
        (500, {"success": False, "error": "boom"}, "unknown"),
        (200, {"success": True, "websites": []}, "no_websites"),
        (200, "<html>not json</html>", "unknown"),
    ],
)
async def test_errors_then_recover(
    hass: HomeAssistant, aioclient_mock, status, body, error
) -> None:
    """Each API failure shows its own message and the user can try again."""
    if isinstance(body, dict):
        aioclient_mock.get(WEBSITES_URL, status=status, json=body)
    else:
        aioclient_mock.get(WEBSITES_URL, status=status, text=body)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    aioclient_mock.clear_requests()
    aioclient_mock.get(WEBSITES_URL, json=ONE_SITE)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_cannot_connect(hass: HomeAssistant, aioclient_mock) -> None:
    """No network: a clear message."""
    aioclient_mock.get(WEBSITES_URL, exc=aiohttp.ClientConnectionError())
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_timeout_is_cannot_connect(hass: HomeAssistant, aioclient_mock) -> None:
    """A timeout is a connection problem too."""
    aioclient_mock.get(WEBSITES_URL, exc=TimeoutError())
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_same_website_twice_aborts(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """One website is connected once."""
    config_entry.add_to_hass(hass)
    aioclient_mock.get(WEBSITES_URL, json=ONE_SITE)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_second_website_is_allowed(
    hass: HomeAssistant, aioclient_mock, config_entry
) -> None:
    """A second website of the same account gets its own agent."""
    config_entry.add_to_hass(hass)
    aioclient_mock.get(WEBSITES_URL, json=TWO_SITES)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WEBSITE_ID: "9"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "help.example"


async def test_development_server_address(
    hass: HomeAssistant, aioclient_mock, monkeypatch
) -> None:
    """ASYNTAI_BASE_URL points the flow at a development server."""
    other = "http://127.0.0.1:8099"
    monkeypatch.setenv("ASYNTAI_BASE_URL", f"{other}/")
    aioclient_mock.get(f"{other}/api/v1/websites/", json=ONE_SITE)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: API_KEY}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_BASE_URL] == f"{other}/"
    assert result["result"].unique_id == f"{other}/|7"


async def test_reauth(hass: HomeAssistant, aioclient_mock, config_entry) -> None:
    """A new key replaces the old one for the same website."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    aioclient_mock.get(WEBSITES_URL, status=401, json={"success": False})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "still-bad"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        WEBSITES_URL,
        json={"success": True, "websites": [{"id": 99, "domain": "other.example"}]},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "other-account"}
    )
    assert result["errors"] == {"base": "website_missing"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(WEBSITES_URL, json=ONE_SITE)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new-key"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_API_KEY] == "new-key"
