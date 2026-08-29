import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock
from app.services.tts import synthesize_speech


@pytest.mark.asyncio
async def test_synthesize_speech_success(mock_settings):
    async def mock_stream():
        yield {"type": "audio", "data": b"fake-mp3-bytes"}

    with patch("app.services.tts.Communicate") as MockCommunicate:
        mock_instance = MagicMock()
        mock_instance.stream.return_value = mock_stream()
        MockCommunicate.return_value = mock_instance
        result = await synthesize_speech("Hello", "en-US-GuyNeural")
    assert result == b"fake-mp3-bytes"


@pytest.mark.asyncio
async def test_synthesize_speech_api_error(mock_settings):
    async def mock_stream():
        raise RuntimeError("TTS synthesis failed")

    with patch("app.services.tts.Communicate") as MockCommunicate:
        mock_instance = MagicMock()
        mock_instance.stream.return_value = mock_stream()
        MockCommunicate.return_value = mock_instance
        with pytest.raises(RuntimeError):
            await synthesize_speech("Hello", "en-IN-NeerjaNeural")
