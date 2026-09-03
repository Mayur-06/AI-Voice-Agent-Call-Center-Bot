import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.tts import synthesize_speech, synthesize_speech_stream, stream_sentences, get_persona_voice_id


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


@pytest.mark.asyncio
async def test_stream_sentences_success(mock_settings):
    mock_manager = MagicMock()
    mock_manager.send_json = AsyncMock()
    mock_manager.send_bytes = AsyncMock()

    async def mock_tts_stream(*args, **kwargs):
        yield b"audio-chunk-1"
        yield b"audio-chunk-2"

    async def sentence_source():
        yield "Hello world.", 0
        yield "How are you?", 1

    with patch("app.services.tts.manager", mock_manager), \
         patch("app.services.tts._append_log") as mock_log, \
         patch("app.services.tts.synthesize_speech_stream", side_effect=mock_tts_stream):
        sentences_sent, tts_first_audio_latency_ms = await stream_sentences("session-1", sentence_source(), "en-US-GuyNeural")

    assert sentences_sent == 2
    assert isinstance(tts_first_audio_latency_ms, int)
    mock_manager.send_json.assert_any_call("session-1", {"type": "status", "message": "speaking", "sentence_index": 0})
    mock_manager.send_json.assert_any_call("session-1", {"type": "sentence_end", "text": "Hello world.", "index": 0})
    mock_manager.send_json.assert_any_call("session-1", {"type": "status", "message": "speaking", "sentence_index": 1})
    mock_manager.send_json.assert_any_call("session-1", {"type": "sentence_end", "text": "How are you?", "index": 1})
    mock_manager.send_bytes.assert_any_call("session-1", b"audio-chunk-1audio-chunk-2")


@pytest.mark.asyncio
async def test_stream_sentences_handles_tts_error(mock_settings):
    mock_manager = MagicMock()
    mock_manager.send_json = AsyncMock()
    mock_manager.send_bytes = AsyncMock()

    async def mock_tts_stream(*args, **kwargs):
        raise RuntimeError("TTS failed")
        yield b"audio"

    async def sentence_source():
        yield "Hello.", 0

    with patch("app.services.tts.manager", mock_manager), \
         patch("app.services.tts._append_log") as mock_log, \
         patch("app.services.tts.synthesize_speech_stream", side_effect=mock_tts_stream):
        sentences_sent, tts_first_audio_latency_ms = await stream_sentences("session-1", sentence_source(), "en-US-GuyNeural")

    assert sentences_sent == 1
    assert tts_first_audio_latency_ms is None
    mock_manager.send_json.assert_any_call("session-1", {"type": "error", "message": "tts_failed:TTS failed"})
