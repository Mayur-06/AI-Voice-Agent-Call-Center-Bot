import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from app.services.session import create_session, save_turn, end_session
from app.routers.sessions import list_sessions


@pytest.mark.asyncio
async def test_create_session(mock_settings):
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": "session-1"}
    ]
    with patch("app.services.session.get_supabase", return_value=mock_supabase):
        session_id = await create_session("persona-1")
    assert session_id == "session-1"


@pytest.mark.asyncio
async def test_save_turn(mock_settings):
    mock_supabase = MagicMock()
    with patch("app.services.session.get_supabase", return_value=mock_supabase):
        await save_turn("session-1", "user", "Hello", sentiment="neutral", latency_ms=100)
    mock_supabase.table.assert_called_with("messages")


@pytest.mark.asyncio
async def test_end_session(mock_settings):
    mock_supabase = MagicMock()
    with patch("app.services.session.get_supabase", return_value=mock_supabase):
        await end_session("session-1")
    calls = [call.args[0] for call in mock_supabase.table.call_args_list]
    assert "sessions" in calls
    assert "call_metrics" in calls


@pytest.mark.asyncio
async def test_list_sessions_handles_missing_voice_id_in_voice_rows(mock_settings):
    mock_supabase = MagicMock()
    session_table = MagicMock()
    personas_table = MagicMock()
    voices_table = MagicMock()

    mock_supabase.table.side_effect = lambda table_name: {
        "sessions": session_table,
        "personas": personas_table,
        "voices": voices_table,
    }[table_name]

    session_table.select.return_value.order.return_value.execute.return_value.data = [
        {
            "id": "session-1",
            "persona_id": "persona-1",
            "selected_voice": "en-US-JennyNeural",
            "started_at": datetime.utcnow(),
        }
    ]
    personas_table.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": "persona-1", "name": "Sales"}
    ]
    voices_table.select.return_value.in_.return_value.execute.return_value.data = [
        {"id": 1, "name": "Jenny (Female, US)"}
    ]

    with patch("app.routers.sessions.get_supabase", return_value=mock_supabase):
        sessions = await list_sessions()

    assert sessions[0]["persona_name"] == "Sales"
    assert sessions[0]["selected_voice_name"] == "Unknown"
