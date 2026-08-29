import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.routers.auth import get_current_user


class MockUser:
    id = "test-user-id"


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: MockUser()
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_list_voices_fallback_when_edge_tts_fails(client):
    with patch("app.routers.voices.list_voices", side_effect=Exception("Edge TTS error")):
        response = client.get("/api/voices")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3
    assert all("voice_id" in v and "name" in v for v in data)


@pytest.mark.asyncio
async def test_list_voices_from_edge_tts(client):
    mock_voices = [
        {
            "Name": "Microsoft George Online (Natural)",
            "ShortName": "en-US-GuyNeural",
            "Gender": "Male",
            "Locale": "en-US",
            "SuggestedCodec": "audio-16khz-32kbitrate-mono-mp3",
            "FriendlyName": "Microsoft George Online (Natural) (en-US)",
            "Status": "GA",
            "VoiceTag": {"ContentCategories": ["Conversation"], "VoicePersonalities": ["Friendly"]},
        }
    ]
    with patch("app.routers.voices.list_voices", return_value=mock_voices):
        response = client.get("/api/voices")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["voice_id"] == "en-US-GuyNeural"
    assert data[0]["preview_url"] is None


@pytest.mark.asyncio
async def test_analytics_endpoint(client):
    with patch("app.routers.analytics.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.execute.return_value.data = []
        mock_supabase.table.return_value.select.return_value.execute.return_value.count = 0
        mock_get_supabase.return_value = mock_supabase
        response = client.get("/api/analytics")
    assert response.status_code == 200
    data = response.json()
    assert "total_sessions" in data
    assert "total_turns" in data
