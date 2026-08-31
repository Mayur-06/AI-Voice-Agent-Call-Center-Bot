import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(r'C:\Users\ktmay\OneDrive\Desktop\AI Voice Agent\backend').resolve()))

from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import WebSocket, WebSocketDisconnect
from app.websocket.handler import router as ws_router

class MockUser:
    id = 'test-user-id'
    email = 'test@example.com'

async def fake_llm_stream(*args, **kwargs):
    try:
        await asyncio.sleep(2)
    except asyncio.CancelledError:
        pass
    yield 'This response should be cancelled.'

async def mock_tts_stream_fn(*args, **kwargs):
    yield b'audio'

async def main():
    mock_ws = AsyncMock(spec=WebSocket)
    mock_ws.query_params = {'token': 'valid-token'}

    audio_chunk = b'\x00\x00' * 960

    mock_ws.receive = AsyncMock(side_effect=[
        {'bytes': audio_chunk},
        {'bytes': audio_chunk},
        WebSocketDisconnect(),
    ])

    with patch('app.websocket.handler.get_current_user') as mock_get_current_user, \
         patch('app.websocket.handler.manager') as mock_manager, \
         patch('app.websocket.handler.create_session', new_callable=AsyncMock) as mock_create_session, \
         patch('app.websocket.handler.end_session', new_callable=AsyncMock) as mock_end_session, \
         patch('app.websocket.handler.VADBuffer') as mock_vad_cls, \
         patch('app.websocket.handler.pcm_to_wav') as mock_convert, \
         patch('app.websocket.handler.decode_to_pcm') as mock_decode, \
         patch('app.websocket.handler.transcribe_audio') as mock_stt, \
         patch('app.websocket.handler.retrieve_context') as mock_rag, \
         patch('app.websocket.handler.generate_response_stream') as mock_llm_stream, \
         patch('app.websocket.handler.synthesize_speech_stream') as mock_tts_stream, \
         patch('app.websocket.handler.save_turn', new_callable=AsyncMock):
        mock_get_current_user.return_value = MockUser()
        mock_vad = MagicMock()
        mock_vad.process = MagicMock(return_value=(b'audio', True))
        mock_vad_cls.return_value = mock_vad
        mock_decode.return_value = b'\x00\x00' * 960
        mock_convert.return_value = b'wav-audio'
        mock_stt.return_value = 'Hello?'
        mock_rag.return_value = []
        mock_llm_stream.return_value = fake_llm_stream()
        mock_tts_stream.return_value = mock_tts_stream_fn()
        mock_create_session.return_value = 'session-1'
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.send_bytes = AsyncMock()
        
        await ws_router.routes[0].endpoint(mock_ws, 'session-1')

    from app.websocket.handler import session_logs
    logs = session_logs.get('session-1', [])
    for entry in logs:
        print(entry['msg'])

asyncio.run(main())
