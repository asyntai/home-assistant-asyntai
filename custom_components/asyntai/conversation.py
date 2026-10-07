"""Asyntai conversation agent."""

from typing import Literal

from homeassistant.components import conversation
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import intent
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AsyntaiConfigEntry
from .api import (
    AsyntaiAuthError,
    AsyntaiConnectionError,
    AsyntaiError,
    AsyntaiLimitError,
    AsyntaiPlanError,
)
from .const import CONF_WEBSITE_ID, DOMAIN, LOGGER


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AsyntaiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the conversation agent of this website."""
    async_add_entities([AsyntaiConversationEntity(entry)])


class AsyntaiConversationEntity(conversation.ConversationEntity):
    """Answer with the knowledge of one Asyntai website."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: AsyntaiConfigEntry) -> None:
        """Bind the agent to its config entry."""
        self.entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Asyntai",
            model="AI agent",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://asyntai.com/dashboard",
        )

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Asyntai answers in the language of the question."""
        return MATCH_ALL

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Send the question to Asyntai and add the answer to the chat log."""
        client = self.entry.runtime_data
        try:
            payload = await client.async_chat(
                user_input.text,
                session_id=f"ha_{chat_log.conversation_id}",
                website_id=int(self.entry.data[CONF_WEBSITE_ID]),
            )
        except AsyntaiAuthError as err:
            self.entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                "Asyntai did not accept the API key. Enter a new key in the integration settings."
            ) from err
        except AsyntaiPlanError as err:
            raise HomeAssistantError(
                "The Asyntai API needs the Starter plan or higher."
            ) from err
        except AsyntaiLimitError as err:
            raise HomeAssistantError(
                "The Asyntai message allowance for this month is used up."
            ) from err
        except AsyntaiConnectionError as err:
            raise HomeAssistantError(f"Could not reach Asyntai: {err}") from err
        except AsyntaiError as err:
            LOGGER.error("Asyntai sent an error: %s", err)
            raise HomeAssistantError(f"Asyntai sent an error: {err}") from err

        answer = payload["response"].strip()
        # The API sends this sentence with the first answer of a conversation
        # only. The person reading or hearing the answer must get it, so it
        # goes in front of that first answer.
        disclosure = (payload.get("ai_disclosure") or "").strip()
        if disclosure:
            answer = f"{disclosure}\n\n{answer}"

        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(agent_id=user_input.agent_id, content=answer)
        )
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(answer)
        return conversation.ConversationResult(
            response=response, conversation_id=chat_log.conversation_id
        )
