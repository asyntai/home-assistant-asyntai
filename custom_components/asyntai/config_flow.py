"""Config flow for the Asyntai integration."""

from collections.abc import Mapping
import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    AsyntaiAuthError,
    AsyntaiClient,
    AsyntaiConnectionError,
    AsyntaiError,
    AsyntaiPlanError,
)
from .const import (
    API_KEY_URL,
    CONF_BASE_URL,
    CONF_WEBSITE_DOMAIN,
    CONF_WEBSITE_ID,
    DEFAULT_BASE_URL,
    DOMAIN,
    LOGGER,
)

KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _site_label(site: dict[str, Any]) -> str:
    """Name a website the way the Asyntai dashboard does."""
    return str(site.get("domain") or f"Website {site['id']}")


class AsyntaiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Connect Home Assistant to one Asyntai website."""

    VERSION = 1

    def __init__(self) -> None:
        """Start with an empty flow."""
        self._api_key = ""
        self._base_url = DEFAULT_BASE_URL
        self._websites: list[dict[str, Any]] = []

    async def _async_fetch_websites(
        self, api_key: str, base_url: str
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Read the website list, or return the error key for the form."""
        client = AsyntaiClient(async_get_clientsession(self.hass), api_key, base_url)
        try:
            websites = await client.async_get_websites()
        except AsyntaiAuthError:
            return [], "invalid_auth"
        except AsyntaiPlanError:
            return [], "plan_required"
        except AsyntaiConnectionError:
            return [], "cannot_connect"
        except AsyntaiError:
            LOGGER.exception("Asyntai sent an error while setting up")
            return [], "unknown"
        if not websites:
            return [], "no_websites"
        return websites, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            # Only for testing against a development server; users never see it.
            base_url = (
                os.environ.get("ASYNTAI_BASE_URL", "").strip() or DEFAULT_BASE_URL
            )
            websites, error = await self._async_fetch_websites(api_key, base_url)
            if error:
                errors["base"] = error
            else:
                self._api_key = api_key
                self._base_url = base_url
                self._websites = websites
                if len(websites) == 1:
                    return await self._async_create_for(websites[0])
                return await self.async_step_website()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): KEY_SELECTOR}),
            errors=errors,
            description_placeholders={"api_key_url": API_KEY_URL},
        )

    async def async_step_website(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick the website whose knowledge answers."""
        if user_input is not None:
            chosen = str(user_input[CONF_WEBSITE_ID])
            for site in self._websites:
                if str(site["id"]) == chosen:
                    return await self._async_create_for(site)

        options = [
            SelectOptionDict(value=str(site["id"]), label=_site_label(site))
            for site in self._websites
        ]
        primary = next(
            (str(site["id"]) for site in self._websites if site.get("is_primary")),
            options[0]["value"],
        )
        return self.async_show_form(
            step_id="website",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_WEBSITE_ID, default=primary): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
        )

    async def _async_create_for(self, site: dict[str, Any]) -> ConfigFlowResult:
        """Create the entry for one website, once per website."""
        await self.async_set_unique_id(f"{self._base_url}|{site['id']}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=_site_label(site),
            data={
                CONF_API_KEY: self._api_key,
                CONF_BASE_URL: self._base_url,
                CONF_WEBSITE_ID: int(site["id"]),
                CONF_WEBSITE_DOMAIN: _site_label(site),
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start a new key prompt after Asyntai refused the old key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key for the same website."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            base_url = entry.data.get(CONF_BASE_URL, DEFAULT_BASE_URL)
            websites, error = await self._async_fetch_websites(api_key, base_url)
            if error:
                errors["base"] = error
            elif not any(
                str(site["id"]) == str(entry.data[CONF_WEBSITE_ID]) for site in websites
            ):
                errors["base"] = "website_missing"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): KEY_SELECTOR}),
            errors=errors,
            description_placeholders={
                "website": entry.title,
                "api_key_url": API_KEY_URL,
            },
        )
