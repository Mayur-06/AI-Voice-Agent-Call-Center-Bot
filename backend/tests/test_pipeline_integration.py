import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json as json_module
import logging
import asyncio
from contextlib import suppress
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, ANY
from fastapi import WebSocket
from httpx import Response
from app.websocket.handler import router as ws_router


logger = logging.getLogger("test_pipeline")


def _mock_response(status_code=200, json_data=None):
    content = json_module.dumps(json_data or {}).encode()
    response = Response(status_code, content=content)
    response.raise_for_status = MagicMock()
    return response


def _make_pcm_chunk(duration_ms: int = 250) -> bytes:
    samples = int(16000 * 2 * (duration_ms / 1000))
    return b"\x00\x00" * (samples // 2)


def _get_session_logs(session_id: str):
    from app.websocket.manager import session_logs
    return list(session_logs.get(session_id, []))


class MockUser:
    id = "anonymous"
    email = "anonymous@example.com"


@pytest.mark.asyncio
async def test_pipeline_routes_to_v2_when_flag_set():
    mock_ws = AsyncMock(spec=WebSocket)

    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.websocket.handler._get_default_persona_id", new_callable=AsyncMock) as mock_get_default_persona, \
         patch("app.websocket.handler._load_session", new_callable=AsyncMock) as mock_load_session, \
         patch("app.websocket.handler._handle_voice_pipeline_v2", new_callable=AsyncMock) as mock_v2_handler, \
         patch("app.websocket.handler.settings") as mock_settings:
        mock_get_default_persona.return_value = "default"
        mock_load_session.return_value = None
        mock_settings.use_new_pipeline = True
        mock_create_session.return_value = "session-1"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.send_bytes = AsyncMock()

        mock_ws.receive = AsyncMock(side_effect=[
            {"type": "websocket.disconnect"},
        ])

        await ws_router.routes[0].endpoint(mock_ws, "session-1")

    mock_v2_handler.assert_called_once_with(mock_ws, "session-1")


@pytest.mark.asyncio
async def test_pipeline_audio_message_routed_to_audio_in_queue():
    from app.orchestration.pipeline import SessionPipelineState
    from app.orchestration.stages import ws_in_task
    from app.services.conversation_mgr import ConversationManager
    from app.services.vad import VADBuffer

    mock_ws = AsyncMock(spec=WebSocket)
    state = SessionPipelineState(
        session_id="sess-1",
        db_session_id="db-1",
        persona_id="p-1",
        voice_id="v-1",
        websocket=mock_ws,
        audio_in_queue=asyncio.Queue(),
        text_in_queue=asyncio.Queue(),
        sentence_queue=asyncio.Queue(),
        audio_out_queue=asyncio.Queue(),
        control_queue=asyncio.Queue(),
        ws_event_queue=asyncio.Queue(),
        conversation_mgr=ConversationManager(),
        vad=VADBuffer(sample_rate=16000),
        speech_detected=asyncio.Event(),
        cancelled_turns=set(),
    )

    audio_chunk = b"\x00\x00" * 320
    mock_ws.receive = AsyncMock(side_effect=[
        {"type": "websocket.receive", "bytes": audio_chunk},
        {"type": "websocket.disconnect"},
    ])

    task = asyncio.create_task(ws_in_task(state))
    await asyncio.sleep(0.2)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert state.audio_in_queue.get_nowait() == audio_chunk


@pytest.mark.asyncio
async def test_pipeline_text_message_routed_to_control_queue():
    from app.orchestration.pipeline import SessionPipelineState
    from app.orchestration.stages import ws_in_task
    from app.services.conversation_mgr import ConversationManager
    from app.services.vad import VADBuffer

    mock_ws = AsyncMock(spec=WebSocket)
    state = SessionPipelineState(
        session_id="sess-1",
        db_session_id="db-1",
        persona_id="p-1",
        voice_id="v-1",
        websocket=mock_ws,
        audio_in_queue=asyncio.Queue(),
        text_in_queue=asyncio.Queue(),
        sentence_queue=asyncio.Queue(),
        audio_out_queue=asyncio.Queue(),
        control_queue=asyncio.Queue(),
        ws_event_queue=asyncio.Queue(),
        conversation_mgr=ConversationManager(),
        vad=VADBuffer(sample_rate=16000),
        speech_detected=asyncio.Event(),
        cancelled_turns=set(),
    )

    mock_ws.receive = AsyncMock(side_effect=[
        {"type": "websocket.receive", "text": '{"type": "transcript", "text": "hello"}'},
        {"type": "websocket.disconnect"},
    ])

    task = asyncio.create_task(ws_in_task(state))
    await asyncio.sleep(0.2)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    event = state.control_queue.get_nowait()
    assert event["type"] == "external_transcript"
    assert event["data"]["text"] == "hello"


@pytest.mark.asyncio
async def test_pipeline_stop_call_routed_to_control_queue():
    from app.orchestration.pipeline import SessionPipelineState
    from app.orchestration.stages import ws_in_task
    from app.services.conversation_mgr import ConversationManager
    from app.services.vad import VADBuffer

    mock_ws = AsyncMock(spec=WebSocket)
    state = SessionPipelineState(
        session_id="sess-1",
        db_session_id="db-1",
        persona_id="p-1",
        voice_id="v-1",
        websocket=mock_ws,
        audio_in_queue=asyncio.Queue(),
        text_in_queue=asyncio.Queue(),
        sentence_queue=asyncio.Queue(),
        audio_out_queue=asyncio.Queue(),
        control_queue=asyncio.Queue(),
        ws_event_queue=asyncio.Queue(),
        conversation_mgr=ConversationManager(),
        vad=VADBuffer(sample_rate=16000),
        speech_detected=asyncio.Event(),
        cancelled_turns=set(),
    )

    mock_ws.receive = AsyncMock(side_effect=[
        {"type": "websocket.receive", "text": '{"type": "stop_call"}'},
    ])

    await ws_in_task(state)

    event = state.control_queue.get_nowait()
    assert event["type"] == "stop_call"



