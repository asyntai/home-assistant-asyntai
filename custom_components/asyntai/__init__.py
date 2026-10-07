"""The Asyntai integration: your website's AI agent as a Home Assistant conversation agent."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    AsyntaiAuthError,
    AsyntaiClient,
    AsyntaiConnectionError,
    AsyntaiError,
    AsyntaiPlanError,
)
from .const import CONF_BASE_URL, CONF_WEBSITE_ID, DEFAULT_BASE_URL

PLATFORMS = [Platform.CONVERSATION]

type AsyntaiConfigEntry = ConfigEntry[AsyntaiClient]


async def async_setup_entry(hass: HomeAssistant, entry: AsyntaiConfigEntry) -> bool:
    """Check the key and the website, then start the conversation agent."""
    client = AsyntaiClient(
        async_get_clientsession(hass),
        entry.data[CONF_API_KEY],
        entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL),
    )
    try:
        websites = await client.async_get_websites()
    except AsyntaiAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except AsyntaiPlanError as err:
        raise ConfigEntryError(str(err)) from err
    except (AsyntaiConnectionError, AsyntaiError) as err:
        raise ConfigEntryNotReady(str(err)) from err

    if not any(
        str(site["id"]) == str(entry.data[CONF_WEBSITE_ID]) for site in websites
    ):
        raise ConfigEntryError(
            f"The website {entry.title} is no longer on this Asyntai account"
        )

    entry.runtime_data = client
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AsyntaiConfigEntry) -> bool:
    """Stop the conversation agent."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
