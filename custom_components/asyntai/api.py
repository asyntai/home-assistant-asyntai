"""Client for the Asyntai public API.

The integration uses two endpoints: the website list, to set up and check the
key, and the chat endpoint, which answers a question from the knowledge of one
website. Both are documented at https://asyntai.com/documentation/api-reference/.
"""

from typing import Any

import aiohttp

from .const import DEFAULT_BASE_URL

REQUEST_TIMEOUT = 60


class AsyntaiError(Exception):
    """The Asyntai API refused a call or sent an unexpected answer."""


class AsyntaiConnectionError(AsyntaiError):
    """The Asyntai API could not be reached."""


class AsyntaiAuthError(AsyntaiError):
    """The API key is wrong or was deleted."""


class AsyntaiPlanError(AsyntaiError):
    """The account plan does not include API access."""


class AsyntaiLimitError(AsyntaiError):
    """The message allowance of the plan is used up."""


class AsyntaiClient:
    """Call the Asyntai API with one API key."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        """Store the session, the key and the server address."""
        self._session = session
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def _request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send one request and return the JSON body of a successful answer."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": "home-assistant-asyntai",
        }
        try:
            async with self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                json=json_body,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                status = response.status
                try:
                    payload = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    payload = None
        except (aiohttp.ClientError, TimeoutError) as err:
            raise AsyntaiConnectionError(
                f"Could not reach Asyntai: {err or type(err).__name__}"
            ) from err

        if status == 401:
            raise AsyntaiAuthError("Asyntai did not accept the API key")
        if status == 403:
            raise AsyntaiPlanError("The Asyntai API needs the Starter plan or higher")
        if status == 429:
            raise AsyntaiLimitError("The Asyntai message allowance is used up")
        if not isinstance(payload, dict):
            raise AsyntaiError(f"Asyntai sent an unexpected answer (HTTP {status})")
        if status >= 400 or not payload.get("success", False):
            raise AsyntaiError(
                payload.get("error") or f"Asyntai API error (HTTP {status})"
            )
        return payload

    async def async_get_websites(self) -> list[dict[str, Any]]:
        """Return the websites (AI agents) on the account."""
        payload = await self._request("GET", "/api/v1/websites/")
        websites = payload.get("websites")
        if not isinstance(websites, list):
            raise AsyntaiError("Asyntai sent an unexpected website list")
        return [site for site in websites if isinstance(site, dict) and "id" in site]

    async def async_chat(
        self, message: str, session_id: str, website_id: int
    ) -> dict[str, Any]:
        """Ask the agent of one website and return the API answer."""
        payload = await self._request(
            "POST",
            "/api/v1/chat/",
            {"message": message, "session_id": session_id, "website_id": website_id},
        )
        if not isinstance(payload.get("response"), str):
            raise AsyntaiError("Asyntai sent an answer without text")
        return payload
