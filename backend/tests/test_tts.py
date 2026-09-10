import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.tts import synthesize_speech, synthesize_speech_stream, get_persona_voice_id


@pytest.mark.asyncio
async def test_get_persona_voice_id_found(mock_settings):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
        {"voice_id": "en-IN-PrabhatNeural"}
    ]
    with patch("app.services.tts.get_supabase", return_value=mock_supabase):
        voice_id = await get_persona_voice_id("persona-1")
    assert voice_id == "en-IN-PrabhatNeural"


@pytest.mark.asyncio
async def test_get_persona_voice_id_missing(mock_settings):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = []
    with patch("app.services.tts.get_supabase", return_value=mock_supabase):
        voice_id = await get_persona_voice_id("missing-persona")
    assert voice_id == "en-IN-NeerjaNeural"


@pytest.mark.asyncio
async def test_get_persona_voice_id_exception(mock_settings):
    mock_supabase = MagicMock()
    mock_supabase.table.side_effect = RuntimeError("db error")
    with patch("app.services.tts.get_supabase", return_value=mock_supabase):
        voice_id = await get_persona_voice_id("persona-1")
    assert voice_id == "en-IN-NeerjaNeural"


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


@pytest.mark.asyncio
async def test_synthesize_speech_stream_yields_chunks(mock_settings):
    async def mock_stream():
        yield {"type": "audio", "data": b"chunk1"}
        yield {"type": "audio", "data": b"chunk2"}

    with patch("app.services.tts.Communicate") as MockCommunicate:
        mock_instance = MagicMock()
        mock_instance.stream.return_value = mock_stream()
        MockCommunicate.return_value = mock_instance
        chunks = []
        async for chunk in synthesize_speech_stream("Hello", "en-US-GuyNeural"):
            chunks.append(chunk)
    assert chunks == [b"chunk1", b"chunk2"]