# test_chat.py
import pytest
from unittest.mock import AsyncMock
from chat import GeminiChat

@pytest.fixture
def fake_client():
    client = AsyncMock()
    client.generate.return_value = "hello back"
    return client

@pytest.mark.asyncio
async def test_send_returns_model_response(fake_client):
    chat = GeminiChat(fake_client)
    result = await chat.send(user_id=1, message="hi")
    assert result == "hello back"

@pytest.mark.asyncio
async def test_history_is_isolated_per_user(fake_client):
    chat = GeminiChat(fake_client)
    await chat.send(1, "user one message")
    await chat.send(2, "user two message")
    assert len(chat.histories[1]) == 2  # user msg + model reply
    assert chat.histories[1][0]["content"] == "user one message"
    assert chat.histories[2][0]["content"] == "user two message"

@pytest.mark.asyncio
async def test_history_trims_to_max(fake_client):
    chat = GeminiChat(fake_client, max_history=4)
    for i in range(5):
        await chat.send(1, f"msg {i}")
    assert len(chat.histories[1]) == 4

@pytest.mark.asyncio
async def test_api_failure_returns_error_message(fake_client):
    fake_client.generate.side_effect = RuntimeError("rate limit")
    chat = GeminiChat(fake_client)
    result = await chat.send(1, "hi")
    assert "Sorry" in result
    # history should still have the user message but no model reply
    assert chat.histories[1][-1]["role"] == "user"