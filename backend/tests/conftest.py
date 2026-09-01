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
        yield mock
