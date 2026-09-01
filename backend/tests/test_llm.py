import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock
from app.services.llm import generate_response, generate_response_stream


def _make_mock_chunk(text: str):
    mock_chunk = MagicMock()
    mock_chunk.text = text
    return mock_chunk


@pytest.mark.asyncio
async def test_generate_response_success(mock_settings):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Generated response"
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.services.llm._client", mock_client):
        result = await generate_response([{"role": "user", "content": "Hello"}], "System prompt")
    assert result == "Generated response"


@pytest.mark.asyncio
async def test_generate_response_multiple_turns(mock_settings):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Reply"
    mock_client.models.generate_content.return_value = mock_response

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
    mock_client.models.generate_content_stream.return_value = [
        _make_mock_chunk("Generated"),
        _make_mock_chunk(" response"),
    ]

    with patch("app.services.llm._client", mock_client):
        chunks = []
        async for chunk in generate_response_stream([{"role": "user", "content": "Hello"}], "System prompt"):
            chunks.append(chunk)
    assert chunks == ["Generated", " response"]


@pytest.mark.asyncio
async def test_generate_response_stream_multiple_turns(mock_settings):
    mock_client = MagicMock()
    mock_client.models.generate_content_stream.return_value = [
        _make_mock_chunk("Reply"),
    ]

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
