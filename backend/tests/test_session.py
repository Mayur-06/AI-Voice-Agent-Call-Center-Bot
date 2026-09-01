import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from app.services.session import create_session, save_turn, end_session


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
    mock_supabase.table.assert_called_with("sessions")
