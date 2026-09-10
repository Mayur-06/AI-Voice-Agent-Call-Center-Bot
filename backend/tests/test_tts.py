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
async def test_synthesize_speech_success(mock_settings, mp3_bytes):
    async def mock_stream():
        yield {"type": "audio", "data": mp3_bytes}

    with patch("app.services.tts.Communicate") as MockCommunicate:
        mock_instance = MagicMock()
        mock_instance.stream.return_value = mock_stream()
        MockCommunicate.return_value = mock_instance
        result = await synthesize_speech("Hello", "en-US-GuyNeural")
    # Edge TTS returns MP3; the browser is sent WAV.
    assert result[:4] == b"RIFF"
    assert result[8:12] == b"WAVE"
    assert len(result) > 44


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
async def test_synthesize_speech_stream_yields_chunks(mock_settings, mp3_bytes):
    """Audio must be emitted progressively, not in one lump at the end."""
    async def mock_stream():
        for i in range(0, len(mp3_bytes), 800):
            yield {"type": "audio", "data": mp3_bytes[i:i + 800]}

    with patch("app.services.tts.Communicate") as MockCommunicate:
        mock_instance = MagicMock()
        mock_instance.stream.return_value = mock_stream()
        MockCommunicate.return_value = mock_instance
        chunks = []
        async for chunk in synthesize_speech_stream("Hello", "en-US-GuyNeural"):
            chunks.append(chunk)

    assert len(chunks) > 1, "TTS buffered the whole sentence instead of streaming"
    for chunk in chunks:
        assert chunk[:4] == b"RIFF", "each chunk must be independently playable"
    pcm_bytes = sum(len(c) - 44 for c in chunks)
    assert 0.8 < pcm_bytes / (16000 * 2) < 1.3


@pytest.mark.asyncio
async def test_synthesize_speech_stream_closes_early_on_barge_in(mock_settings, mp3_bytes):
    """Closing the generator mid-sentence must not deadlock the decoder."""
    import asyncio

    async def mock_stream():
        for i in range(0, len(mp3_bytes), 400):
            yield {"type": "audio", "data": mp3_bytes[i:i + 400]}
            await asyncio.sleep(0)

    with patch("app.services.tts.Communicate") as MockCommunicate:
        mock_instance = MagicMock()
        mock_instance.stream.return_value = mock_stream()
        MockCommunicate.return_value = mock_instance
        gen = synthesize_speech_stream("Hello", "en-US-GuyNeural")
        first = await gen.__anext__()
        assert first[:4] == b"RIFF"
        await asyncio.wait_for(gen.aclose(), timeout=5)