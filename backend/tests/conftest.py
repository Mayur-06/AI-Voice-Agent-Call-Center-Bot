import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.config.settings") as mock:
        mock.groq_api_key = "test-groq-key"
        mock.google_api_key = "test-google-key"
        mock.supabase_url = "https://test.supabase.co"
        mock.supabase_anon_key = "test-anon-key"
        mock.supabase_service_role_key = "test-service-role-key"
        mock.chromadb_url = "http://localhost:8001"
        mock.audio_sample_rate = 16000
        mock.vad_aggressiveness = 2
        mock.silence_threshold_ms = 1500
        mock.audio_chunk_ms = 250
        mock.gemini_model = "gemini-1.5-flash"
        mock.hf_token = ""
        mock.hf_hub_disable_symlinks_warning = False
        mock.embedding_device = "cpu"
        mock.ws_heartbeat_interval_s = 20
        mock.ws_receive_timeout_s = 180
        mock.ws_max_concurrent_audio_tasks = 32
        mock.ws_audio_executor_workers = 4
        mock.ws_embedding_executor_workers = 2
        mock.ws_queue_max_size = 256
        mock.pinecone_api_key = ""
        mock.pinecone_index_name = "voice-agent-documents"
        mock.filler_threshold_ms = 1500
        mock.use_new_pipeline = False
        yield mock


@pytest.fixture(scope="session")
def mp3_bytes() -> bytes:
    """A real, decodable MP3 (3s of 440 Hz tone).

    Longer than the trailing-silence hold window in synthesize_speech_stream,
    so progressive streaming is observable.

    The TTS tests previously fed literal b"fake-mp3-bytes" into a code path
    that decodes audio, so they could only ever fail.
    """
    import io
    import math
    import av
    import numpy as np

    buf = io.BytesIO()
    container = av.open(buf, mode="w", format="mp3")
    stream = container.add_stream("mp3", rate=44100)
    stream.layout = "mono"
    sr = 44100
    t = np.arange(int(sr * 3.0), dtype=np.float32) / sr
    tone = (np.sin(2 * math.pi * 440 * t) * 20000).astype(np.int16).reshape(1, -1)
    frame = av.AudioFrame.from_ndarray(tone, format="s16", layout="mono")
    frame.rate = sr
    for packet in stream.encode(frame):
        container.mux(packet)
    for packet in stream.encode(None):
        container.mux(packet)
    container.close()
    return buf.getvalue()
