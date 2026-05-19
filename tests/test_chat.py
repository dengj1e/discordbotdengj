import pytest
from unittest.mock import MagicMock
from commands import ask_gemini, truncate_for_discord


@pytest.fixture
def fake_client():
    client = MagicMock()
    response = MagicMock()
    response.text = "AI response"
    client.models.generate_content.return_value = response
    return client


async def test_returns_model_response(fake_client):
    histories = {}
    result = await ask_gemini(fake_client, histories, user_id=1, question="hi")
    assert result == "AI response"


async def test_history_records_user_then_model(fake_client):
    histories = {}
    await ask_gemini(fake_client, histories, 1, "hello")
    assert histories[1] == [
        {"role": "user", "parts": [{"text": "hello"}]},
        {"role": "model", "parts": [{"text": "AI response"}]},
    ]


async def test_history_is_per_user(fake_client):
    histories = {}
    await ask_gemini(fake_client, histories, 1, "from user one")
    await ask_gemini(fake_client, histories, 2, "from user two")
    assert histories[1][0]["parts"][0]["text"] == "from user one"
    assert histories[2][0]["parts"][0]["text"] == "from user two"


async def test_history_caps_at_max(fake_client):
    histories = {}
    for i in range(5):
        await ask_gemini(fake_client, histories, 1, f"msg {i}", max_history=4)
    assert len(histories[1]) == 4


async def test_full_history_sent_to_gemini(fake_client):
    histories = {}
    await ask_gemini(fake_client, histories, 1, "first")
    await ask_gemini(fake_client, histories, 1, "second")
    second_call = fake_client.models.generate_content.call_args_list[1]
    assert len(second_call.kwargs["contents"]) == 3


def test_truncate_under_limit_unchanged():
    assert truncate_for_discord("short") == "short"


def test_truncate_over_limit_adds_ellipsis():
    result = truncate_for_discord("a" * 3000)
    assert len(result) == 2000
    assert result.endswith("...")
