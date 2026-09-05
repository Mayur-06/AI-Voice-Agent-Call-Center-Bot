import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.llm import generate_response, generate_response_stream, get_persona_system_prompt


def _make_mock_chunk(text: str):
    mock_chunk = MagicMock()
    mock_chunk.text = text
    return mock_chunk


@pytest.mark.asyncio
async def test_get_persona_system_prompt_found(mock_settings):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"system_prompt": "You are a customer support agent."}
    ]
    with patch("app.services.llm.get_supabase", return_value=mock_supabase):
        prompt = await get_persona_system_prompt("persona-1")
    assert prompt == "You are a customer support agent."


@pytest.mark.asyncio
async def test_get_persona_system_prompt_missing(mock_settings):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch("app.services.llm.get_supabase", return_value=mock_supabase):
        prompt = await get_persona_system_prompt("missing-persona")
    assert prompt == "You are a helpful voice assistant."


@pytest.mark.asyncio
async def test_get_persona_system_prompt_exception(mock_settings):
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = RuntimeError("db error")
    with patch("app.services.llm.get_supabase", return_value=mock_supabase):
        prompt = await get_persona_system_prompt("persona-1")
    assert prompt == "You are a helpful voice assistant."


@pytest.mark.asyncio
async def test_generate_response_success(mock_settings):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Generated response"
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch("app.services.llm._client", mock_client):
        result = await generate_response([{"role": "user", "content": "Hello"}], "System prompt")
    assert result == "Generated response"


@pytest.mark.asyncio
async def test_generate_response_multiple_turns(mock_settings):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Reply"
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    messages = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "How are you?"},
    ]
    with patch("app.services.llm._client", mock_client):
        result = await generate_response(messages, "System prompt")
    assert result == "Reply"


@pytest.mark.asyncio
async def test_generate_response_stream_success(mock_settings):
    mock_client = MagicMock()

    class _MockAsyncIter:
        def __init__(self, items):
            self._items = list(items)
            self._index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._items):
                raise StopAsyncIteration
            item = self._items[self._index]
            self._index += 1
            return item

    mock_client.aio.models.generate_content_stream = MagicMock(return_value=_MockAsyncIter([
        _make_mock_chunk("Generated"),
        _make_mock_chunk(" response"),
    ]))

    with patch("app.services.llm._client", mock_client):
        chunks = []
        async for chunk in generate_response_stream([{"role": "user", "content": "Hello"}], "System prompt"):
            chunks.append(chunk)
    assert chunks == ["Generated", " response"]


@pytest.mark.asyncio
async def test_generate_response_stream_multiple_turns(mock_settings):
    mock_client = MagicMock()

    class _MockAsyncIter:
        def __init__(self, items):
            self._items = list(items)
            self._index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._items):
                raise StopAsyncIteration
            item = self._items[self._index]
            self._index += 1
            return item

    mock_client.aio.models.generate_content_stream = MagicMock(return_value=_MockAsyncIter([
        _make_mock_chunk("Reply"),
    ]))

    messages = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "How are you?"},
    ]
    with patch("app.services.llm._client", mock_client):
        chunks = []
        async for chunk in generate_response_stream(messages, "System prompt"):
            chunks.append(chunk)
    assert chunks == ["Reply"]
