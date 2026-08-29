import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json as json_module
import pytest
from unittest.mock import patch, MagicMock
from httpx import Response
from app.services.stt import transcribe_audio


def _mock_response(status_code=200, json_data=None):
    content = json_module.dumps(json_data or {}).encode()
    response = Response(status_code, content=content)
    response.raise_for_status = MagicMock()
    return response


@pytest.mark.asyncio
async def test_transcribe_audio_success(mock_settings):
    mock_response = _mock_response(json_data={"text": "Hello world"})
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        result = await transcribe_audio(b"fake-audio-bytes")
    assert result == "Hello world"


@pytest.mark.asyncio
async def test_transcribe_audio_empty_result(mock_settings):
    mock_response = _mock_response(json_data={"text": ""})
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        result = await transcribe_audio(b"fake-audio-bytes")
    assert result == ""


@pytest.mark.asyncio
async def test_transcribe_audio_api_error(mock_settings):
    mock_response = _mock_response(status_code=401, json_data={"error": "Unauthorized"})
    mock_response.raise_for_status.side_effect = Exception("HTTP error")
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        with pytest.raises(Exception):
            await transcribe_audio(b"fake-audio-bytes")
