import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_create_session(client):
    with patch("app.routers.sessions.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "session-1", "persona_id": "persona-1", "user_id": "test-user-id", "started_at": "2024-01-01T00:00:00", "metadata": {}}
        ]
        mock_get_supabase.return_value = mock_supabase
        response = client.post("/api/sessions", json={"persona_id": "persona-1"})
    assert response.status_code == 200
    assert response.json()["id"] == "session-1"


@pytest.mark.asyncio
async def test_list_sessions(client):
    with patch("app.routers.sessions.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.order.return_value.execute.return_value.data = [
            {"id": "session-1", "persona_id": "persona-1", "user_id": "test-user-id", "started_at": "2024-01-01T00:00:00", "metadata": {}}
        ]
        mock_get_supabase.return_value = mock_supabase
        response = client.get("/api/sessions")
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_get_session(client):
    with patch("app.routers.sessions.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "session-1", "persona_id": "persona-1", "user_id": "test-user-id", "started_at": "2024-01-01T00:00:00", "metadata": {}}
        ]
        mock_get_supabase.return_value = mock_supabase
        response = client.get("/api/sessions/session-1")
    assert response.status_code == 200
    assert response.json()["id"] == "session-1"


@pytest.mark.asyncio
async def test_get_session_not_found(client):
    with patch("app.routers.sessions.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        mock_get_supabase.return_value = mock_supabase
        response = client.get("/api/sessions/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_session(client):
    with patch("app.routers.sessions.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "session-1"}
        ]
        mock_supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value.data = []
        mock_get_supabase.return_value = mock_supabase
        response = client.delete("/api/sessions/session-1")
    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}


@pytest.mark.asyncio
async def test_send_message(client):
    with patch("app.routers.sessions.get_supabase") as mock_get_supabase, \
         patch("app.routers.sessions.save_turn", new_callable=AsyncMock), \
         patch("app.routers.sessions.generate_response", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = "Hello there!"
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "session-1"}
        ]
        mock_get_supabase.return_value = mock_supabase
        response = client.post("/api/sessions/session-1/message", json={"text": "Hi"})
    assert response.status_code == 200
    assert response.json()["text"] == "Hello there!"


@pytest.mark.asyncio
async def test_get_transcript(client):
    with patch("app.routers.sessions.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "session-1"}
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
            {"id": "turn-1", "session_id": "session-1", "speaker": "user", "text": "Hello", "timestamp": "2024-01-01T00:00:00"}
        ]
        mock_get_supabase.return_value = mock_supabase
        response = client.get("/api/sessions/session-1/transcript")
    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.asyncio
async def test_get_summary(client):
    with patch("app.routers.sessions.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "session-1"}
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        mock_get_supabase.return_value = mock_supabase
        response = client.get("/api/sessions/session-1/summary")
    assert response.status_code == 200
    assert response.json()["summary"] == "Summary not yet implemented"


@pytest.mark.asyncio
async def test_get_sentiment(client):
    with patch("app.routers.sessions.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "session-1"}
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"sentiment": "positive", "timestamp": "2024-01-01T00:00:00"}
        ]
        mock_get_supabase.return_value = mock_supabase
        response = client.get("/api/sessions/session-1/sentiment")
    assert response.status_code == 200
    assert response.json()["sentiment_timeline"][0]["sentiment"] == "positive"


@pytest.mark.asyncio
async def test_get_metrics(client):
    with patch("app.routers.sessions.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "session-1"}
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"latency_ms": 100, "interrupted": False},
            {"latency_ms": 200, "interrupted": True},
        ]
        mock_get_supabase.return_value = mock_supabase
        response = client.get("/api/sessions/session-1/metrics")
    assert response.status_code == 200
    metrics = response.json()["metrics"]
    assert metrics["turns_count"] == 2
    assert metrics["avg_latency_ms"] == 150.0
    assert metrics["interruptions"] == 1


@pytest.mark.asyncio
async def test_get_metrics_no_turns(client):
    with patch("app.routers.sessions.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "session-1"}
        ]
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
        mock_get_supabase.return_value = mock_supabase
        response = client.get("/api/sessions/session-1/metrics")
    assert response.status_code == 200
    assert response.json()["metrics"]["note"] is not None


@pytest.mark.asyncio
async def test_get_recording(client):
    with patch("app.routers.sessions.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"id": "session-1"}
        ]
        mock_get_supabase.return_value = mock_supabase
        response = client.get("/api/sessions/session-1/recording")
    assert response.status_code == 200
    assert response.json()["recording_url"] is None
