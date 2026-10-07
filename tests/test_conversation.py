"""Tests for the Asyntai conversation agent."""

import json

import aiohttp
import pytest

from homeassistant.components import conversation
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import chat_session, intent
from homeassistant.setup import async_setup_component

from .conftest import CHAT_URL, ONE_SITE, WEBSITES_URL

AGENT = "conversation.shop_example"


@pytest.fixture
async def loaded(hass: HomeAssistant, aioclient_mock, config_entry):
    """A loaded entry with the conversation component running."""
    assert await async_setup_component(hass, "conversation", {})
    aioclient_mock.get(WEBSITES_URL, json=ONE_SITE)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def _ask(hass, text, conversation_id=None, language="en"):
    return await conversation.async_converse(
        hass, text, conversation_id, Context(), language=language, agent_id=AGENT
    )


def _chat_bodies(aioclient_mock):
    return [
        json.loads(call[2]) if isinstance(call[2], (str, bytes)) else call[2]
        for call in aioclient_mock.mock_calls
        if str(call[1]) == CHAT_URL
    ]


async def test_agent_is_listed(hass: HomeAssistant, loaded) -> None:
    """Home Assistant offers the website as a conversation agent for every language."""
    info = conversation.async_get_agent_info(hass, AGENT)
    assert info is not None
    assert info.id == AGENT
    state = hass.states.get(AGENT)
    assert state is not None
    assert state.attributes["friendly_name"] == "shop.example"
    agent = hass.data["entity_components"]["conversation"].get_entity(AGENT)
    assert agent.supported_languages == "*"


async def test_answer_and_follow_up(
    hass: HomeAssistant, aioclient_mock, loaded
) -> None:
    """The answer comes back as speech; the follow-up keeps the same chat session."""
    aioclient_mock.post(
        CHAT_URL,
        json={
            "success": True,
            "response": "We ship to all EU countries in 2-4 days.",
            "session_id": "x",
            "ai_disclosure": "",
        },
    )
    result = await _ask(hass, "Do you ship to Germany?")
    assert result.response.response_type is intent.IntentResponseType.ACTION_DONE
    assert (
        result.response.speech["plain"]["speech"]
        == "We ship to all EU countries in 2-4 days."
    )
    first_id = result.conversation_id
    assert first_id

    result = await _ask(hass, "And to Norway?", conversation_id=first_id)
    assert result.conversation_id == first_id

    bodies = _chat_bodies(aioclient_mock)
    assert [b["message"] for b in bodies] == [
        "Do you ship to Germany?",
        "And to Norway?",
    ]
    assert {b["website_id"] for b in bodies} == {7}
    assert bodies[0]["session_id"] == bodies[1]["session_id"] == f"ha_{first_id}"


async def test_new_conversation_new_session(
    hass: HomeAssistant, aioclient_mock, loaded
) -> None:
    """Two separate conversations do not share Asyntai history."""
    aioclient_mock.post(CHAT_URL, json={"success": True, "response": "Hi"})
    first = await _ask(hass, "Hello")
    second = await _ask(hass, "Hello")
    assert first.conversation_id != second.conversation_id
    bodies = _chat_bodies(aioclient_mock)
    assert bodies[0]["session_id"] != bodies[1]["session_id"]


async def test_disclosure_goes_first(
    hass: HomeAssistant, aioclient_mock, loaded
) -> None:
    """The AI notice the API sends is shown before the first answer."""
    aioclient_mock.post(
        CHAT_URL,
        json={
            "success": True,
            "response": "Opening hours are 9 to 17.",
            "ai_disclosure": "You're chatting with an AI assistant.",
        },
    )
    result = await _ask(hass, "When are you open?")
    assert (
        result.response.speech["plain"]["speech"]
        == "You're chatting with an AI assistant.\n\nOpening hours are 9 to 17."
    )


async def test_language_passes_through(
    hass: HomeAssistant, aioclient_mock, loaded
) -> None:
    """A question in Czech goes to Asyntai unchanged."""
    aioclient_mock.post(CHAT_URL, json={"success": True, "response": "Ano, posíláme."})
    result = await _ask(hass, "Posíláte do Brna?", language="cs")
    assert result.response.speech["plain"]["speech"] == "Ano, posíláme."
    assert _chat_bodies(aioclient_mock)[0]["message"] == "Posíláte do Brna?"


async def test_chat_log_holds_both_sides(
    hass: HomeAssistant, aioclient_mock, loaded
) -> None:
    """The Home Assistant chat log stores the question and the answer."""
    aioclient_mock.post(CHAT_URL, json={"success": True, "response": "Yes."})
    captured = {}
    result = await _ask(hass, "Is it in stock?")

    with (
        chat_session.async_get_chat_session(hass, result.conversation_id) as session,
        conversation.async_get_chat_log(hass, session) as chat_log,
    ):
        captured["roles"] = [c.role for c in chat_log.content]
        captured["texts"] = [getattr(c, "content", None) for c in chat_log.content]
    assert captured["roles"][-2:] == ["user", "assistant"]
    assert captured["texts"][-2:] == ["Is it in stock?", "Yes."]


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"status": 403, "json": {"success": False}}, "Starter plan"),
        (
            {"status": 429, "json": {"success": False, "limit_reached": True}},
            "allowance",
        ),
        ({"exc": aiohttp.ClientConnectionError()}, "Could not reach Asyntai"),
        ({"exc": TimeoutError()}, "Could not reach Asyntai"),
        (
            {"status": 503, "json": {"success": False, "error": "AI service error: x"}},
            "AI service error",
        ),
        ({"status": 200, "json": {"success": True}}, "without text"),
        ({"status": 502, "text": "<html>Bad gateway</html>"}, "unexpected answer"),
    ],
)
async def test_errors_are_spoken(
    hass: HomeAssistant, aioclient_mock, loaded, kwargs, fragment
) -> None:
    """Every failure gives the user a clear sentence, never a crash."""
    aioclient_mock.post(CHAT_URL, **kwargs)
    result = await _ask(hass, "Question")
    assert result.response.response_type is intent.IntentResponseType.ERROR
    assert fragment in result.response.speech["plain"]["speech"]


async def test_bad_key_during_chat_starts_reauth(
    hass: HomeAssistant, aioclient_mock, loaded
) -> None:
    """A key deleted after setup: the user hears why and gets a new-key prompt."""
    aioclient_mock.post(CHAT_URL, status=401, json={"success": False})
    result = await _ask(hass, "Question")
    assert result.response.response_type is intent.IntentResponseType.ERROR
    assert "API key" in result.response.speech["plain"]["speech"]
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]
