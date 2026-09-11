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
    assert 2.5 < pcm_bytes / (16000 * 2) < 3.3


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

@pytest.mark.asyncio
async def test_synthesize_speech_stream_trims_edge_tts_silence_padding(mock_settings):
    """Edge TTS pads each utterance with leading and trailing silence.

    Measured against the live service at roughly 0.26s leading and 0.86s
    trailing. Synthesising per sentence meant ~1.1s of dead air at every
    sentence boundary, which is a large part of why the agent sounded sluggish.
    """
    import io
    import math
    import av
    import numpy as np

    # 0.3s silence, 1.5s tone, 0.9s silence - the shape Edge TTS returns.
    sr = 44100
    silence_a = np.zeros(int(sr * 0.3), dtype=np.int16)
    t = np.arange(int(sr * 1.5), dtype=np.float32) / sr
    tone = (np.sin(2 * math.pi * 440 * t) * 20000).astype(np.int16)
    silence_b = np.zeros(int(sr * 0.9), dtype=np.int16)
    full = np.concatenate([silence_a, tone, silence_b]).reshape(1, -1)

    buf = io.BytesIO()
    container = av.open(buf, mode="w", format="mp3")
    stream = container.add_stream("mp3", rate=sr)
    stream.layout = "mono"
    frame = av.AudioFrame.from_ndarray(full, format="s16", layout="mono")
    frame.rate = sr
    for packet in stream.encode(frame):
        container.mux(packet)
    for packet in stream.encode(None):
        container.mux(packet)
    container.close()
    padded_mp3 = buf.getvalue()

    async def mock_stream():
        for i in range(0, len(padded_mp3), 800):
            yield {"type": "audio", "data": padded_mp3[i:i + 800]}

    with patch("app.services.tts.Communicate") as MockCommunicate:
        instance = MagicMock()
        instance.stream.return_value = mock_stream()
        MockCommunicate.return_value = instance
        pcm = b""
        async for chunk in synthesize_speech_stream("tone", "en-US-GuyNeural"):
            pcm += chunk[44:]

    duration = len(pcm) / (16000 * 2)
    # 2.7s in, ~1.5s of speech plus a small deliberate gap out.
    assert 1.4 < duration < 1.8, f"expected padding removed, got {duration:.2f}s"

    samples = np.frombuffer(pcm, dtype="<i2")
    voiced = np.flatnonzero(np.abs(samples) > 300)
    assert voiced.size, "trimming removed the speech itself"
    assert voiced[0] / 16000 < 0.06, "leading silence was not trimmed"
    assert (samples.size - voiced[-1]) / 16000 < 0.16, "trailing silence was not trimmed"
