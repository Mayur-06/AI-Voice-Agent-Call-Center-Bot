import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock
from httpx import Response
from app.services.llm import generate_response


def _mock_response(status_code=200, json_data=None):
    response = Response(status_code, json=json_data)
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.asyncio
async def test_generate_response_success(mock_settings):
    mock_response = _mock_response(json_data={
        "candidates": [{"content": {"parts": [{"text": "Generated response"}]}}]
    })
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        result = await generate_response([{"role": "user", "content": "Hello"}], "System prompt")
    assert result == "Generated response"


@pytest.mark.asyncio
async def test_generate_response_multiple_turns(mock_settings):
    mock_response = _mock_response(json_data={
        "candidates": [{"content": {"parts": [{"text": "Reply"}]}}]
    })
    messages = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
        {"role": "user", "content": "How are you?"},
    ]
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        result = await generate_response(messages, "System prompt")
    assert result == "Reply"
