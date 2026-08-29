import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.routers.auth import get_current_user


class MockUser:
    id = "test-user-id"


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: MockUser()
    return TestClient(app)


@pytest.mark.asyncio
async def test_analytics_empty(client):
    with patch("app.routers.analytics.get_supabase") as mock_get_supabase:
        mock_supabase = MagicMock()
        mock_supabase.table.return_value.select.return_value.execute.return_value.data = []
        mock_supabase.table.return_value.select.return_value.execute.return_value.count = 0
        mock_get_supabase.return_value = mock_supabase
        response = client.get("/api/analytics")
    assert response.status_code == 200
    data = response.json()
    assert data["total_sessions"] == 0
    assert data["total_turns"] == 0
    assert data["avg_latency_ms"] == 0.0
    assert data["interruption_count"] == 0
    assert data["avg_session_duration_s"] == 0.0
    assert data["sentiment_breakdown"] == {}


@pytest.mark.asyncio
async def test_analytics_with_data(client):
    now = datetime.now(timezone.utc)
    with patch("app.routers.analytics.get_supabase") as mock_get_supabase, \
         patch("app.routers.analytics.datetime") as mock_datetime:
        mock_datetime.now.return_value = now
        mock_datetime.fromisoformat.side_effect = lambda s: datetime.fromisoformat(s)
        mock_supabase = MagicMock()

        def make_execute(data, count=None):
            m = MagicMock()
            m.data = data
            m.count = count
            return m

        started = now - timedelta(days=1)
        ended = started + timedelta(seconds=10)
        mock_supabase.table.return_value.select.return_value.execute.side_effect = [
            make_execute([
                {"id": "s1", "started_at": started.isoformat(), "ended_at": ended.isoformat()},
                {"id": "s2", "started_at": (now - timedelta(days=3)).isoformat(), "ended_at": None},
            ], count=2),
            make_execute([
                {"id": "t1", "session_id": "s1", "latency_ms": 100, "interrupted": False, "sentiment": "positive"},
                {"id": "t2", "session_id": "s1", "latency_ms": 200, "interrupted": True, "sentiment": "neutral"},
            ]),
        ]
        mock_get_supabase.return_value = mock_supabase
        response = client.get("/api/analytics")
    assert response.status_code == 200
    data = response.json()
    assert data["total_sessions"] == 2
    assert data["total_turns"] == 2
    assert data["avg_latency_ms"] == 150.0
    assert data["interruption_count"] == 1
    assert data["avg_session_duration_s"] == 10.0
    assert data["sentiment_breakdown"] == {"positive": 1, "neutral": 1}
