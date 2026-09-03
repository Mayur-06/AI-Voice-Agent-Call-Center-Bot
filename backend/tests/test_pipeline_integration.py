import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json as json_module
import logging
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, ANY
from fastapi import WebSocket, WebSocketDisconnect
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


def _vad_side_effect(audio_chunk: bytes):
    frame_count = 0
    max_frames = int(len(audio_chunk) / int(16000 * 2 * (30 / 1000)))

    def side_effect(frame):
        nonlocal frame_count
        frame_count += 1
        if frame_count >= max_frames:
            return audio_chunk, True
        return None, False

    return side_effect


def _get_session_logs(session_id: str):
    from app.websocket.manager import session_logs
    return list(session_logs.get(session_id, []))


class MockUser:
    id = "anonymous"
    email = "anonymous@example.com"


@pytest.mark.asyncio
async def test_pipeline_audio_to_llm_to_speech():
    mock_ws = AsyncMock(spec=WebSocket)

    audio_chunk = _make_pcm_chunk(250)

    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.services.voice_pipeline.manager", mock_manager), \
         patch("app.services.tts.manager", mock_manager), \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.websocket.handler.VADBuffer") as mock_vad_cls, \
         patch("app.websocket.handler.pcm_to_wav") as mock_convert, \
         patch("app.websocket.handler.decode_to_pcm") as mock_decode, \
         patch("app.websocket.handler.transcribe_audio") as mock_stt, \
         patch("app.websocket.handler.save_session_recording", new_callable=AsyncMock), \
         patch("app.services.voice_pipeline.analyze_sentiment", new_callable=AsyncMock) as mock_analyze_sentiment, \
         patch("app.services.voice_pipeline.retrieve_relevant_chunks", new_callable=AsyncMock) as mock_rag, \
         patch("app.services.voice_pipeline.generate_response_stream") as mock_llm_stream, \
         patch("app.services.voice_pipeline.split_sentences", new_callable=AsyncMock) as mock_split_sentences, \
         patch("app.services.tts.synthesize_speech_stream") as mock_tts_stream, \
         patch("app.services.voice_pipeline.save_turn", new_callable=AsyncMock), \
         patch("app.services.voice_pipeline.get_persona_system_prompt", new_callable=AsyncMock) as mock_get_prompt, \
         patch("app.websocket.handler.get_persona_voice_id", new_callable=AsyncMock) as mock_get_voice, \
         patch("app.websocket.handler._get_default_persona_id", new_callable=AsyncMock) as mock_get_default_persona, \
         patch("app.websocket.handler._load_session", new_callable=AsyncMock) as mock_load_session:
        mock_get_voice.return_value = "en-IN-NeerjaNeural"
        mock_get_prompt.return_value = "System prompt for default"
        mock_get_default_persona.return_value = "default"
        mock_load_session.return_value = None

        mock_vad = MagicMock()
        mock_vad.process = MagicMock(side_effect=_vad_side_effect(audio_chunk))
        mock_vad_cls.return_value = mock_vad

        mock_decode.return_value = audio_chunk
        mock_convert.return_value = b"wav-audio"
        mock_stt.return_value = "What is in the document?"
        mock_rag.return_value = [("policy.pdf", "Context from document: policy is 20 days.")]

        async def mock_llm_stream_fn(*args, **kwargs):
            yield "According to the document, the policy is 20 days."

        mock_llm_stream.return_value = mock_llm_stream_fn()

        async def mock_tts_stream_fn(*args, **kwargs):
            yield b"tts-audio-bytes"

        mock_tts_stream.return_value = mock_tts_stream_fn()

        mock_analyze_sentiment.return_value = "neutral"
        mock_split_sentences.return_value = ["According to the document, the policy is 20 days."]

        mock_create_session.return_value = "session-1"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.send_bytes = AsyncMock()

        mock_ws.receive = AsyncMock(side_effect=[
            {"bytes": audio_chunk},
            WebSocketDisconnect(),
        ])

        await ws_router.routes[0].endpoint(mock_ws, "session-1")

    logs = _get_session_logs("session-1")
    messages = [entry["msg"] for entry in logs]
    assert any("WS connected" in m for m in messages)
    assert any("WS status connected" in m for m in messages)
    assert any("WS db session created" in m for m in messages)
    assert any("WS audio chunk" in m for m in messages)
    assert any("WS speech ended" in m for m in messages)
    assert any("WS STT" in m and "What is in the document?" in m for m in messages)
    assert any("WS RAG context" in m for m in messages)
    assert any("WS LLM stream started" in m for m in messages)
    assert any("WS TTS sentence" in m for m in messages)
    assert any("WS sentence sent" in m for m in messages)
    assert any("WS response ready" in m for m in messages)
    assert any("WS disconnected" in m for m in messages)

    mock_convert.assert_called_once()
    mock_stt.assert_called_once()
    mock_rag.assert_called_once()
    mock_llm_stream.assert_called_once()
    mock_tts_stream.assert_called_once()
    mock_create_session.assert_called_once_with(
        persona_id="default",
        user_id=ANY,
        session_id="session-1",
    )
    mock_manager.send_bytes.assert_called_once_with("session-1", b"tts-audio-bytes")
    mock_manager.send_json.assert_any_call("session-1", {
        "type": "sentence_end",
        "text": "According to the document, the policy is 20 days.",
        "index": 0,
    })


@pytest.mark.asyncio
async def test_pipeline_text_transcript_flow():
    mock_ws = AsyncMock(spec=WebSocket)

    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.services.voice_pipeline.manager", mock_manager), \
         patch("app.services.tts.manager", mock_manager), \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.services.voice_pipeline.analyze_sentiment", new_callable=AsyncMock) as mock_analyze_sentiment, \
         patch("app.services.voice_pipeline.retrieve_relevant_chunks", new_callable=AsyncMock) as mock_rag, \
         patch("app.services.voice_pipeline.generate_response_stream") as mock_llm_stream, \
         patch("app.services.voice_pipeline.split_sentences", new_callable=AsyncMock) as mock_split_sentences, \
         patch("app.services.tts.synthesize_speech_stream") as mock_tts_stream, \
         patch("app.services.voice_pipeline.save_turn", new_callable=AsyncMock), \
         patch("app.services.voice_pipeline.get_persona_system_prompt", new_callable=AsyncMock) as mock_get_prompt, \
         patch("app.websocket.handler.get_persona_voice_id", new_callable=AsyncMock) as mock_get_voice, \
         patch("app.websocket.handler._get_default_persona_id", new_callable=AsyncMock) as mock_get_default_persona, \
         patch("app.websocket.handler._load_session", new_callable=AsyncMock) as mock_load_session:
        mock_get_voice.return_value = "en-IN-NeerjaNeural"
        mock_get_prompt.return_value = "System prompt for default"
        mock_get_default_persona.return_value = "default"
        mock_load_session.return_value = None

        mock_rag.return_value = [("refunds.pdf", "Document says refunds take 5-7 days.")]

        async def mock_llm_stream_fn(*args, **kwargs):
            yield "Refunds take 5-7 business days."

        mock_llm_stream.return_value = mock_llm_stream_fn()

        async def mock_tts_stream_fn(*args, **kwargs):
            yield b"tts-audio"

        mock_tts_stream.return_value = mock_tts_stream_fn()

        mock_analyze_sentiment.return_value = "neutral"
        mock_split_sentences.return_value = ["Refunds take 5-7 business days."]

        mock_create_session.return_value = "session-1"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.send_bytes = AsyncMock()

        mock_ws.receive = AsyncMock(side_effect=[
            {"text": '{"type": "transcript", "text": "When is my refund?"}'},
            WebSocketDisconnect(),
        ])

        await ws_router.routes[0].endpoint(mock_ws, "session-1")

    logs = _get_session_logs("session-1")
    messages = [entry["msg"] for entry in logs]
    assert any("WS text message session=session-1 type=transcript" in m for m in messages)
    assert any("WS transcript session=session-1 text=When is my refund?" in m for m in messages)
    assert any("WS RAG context session=session-1 chunks=1" in m for m in messages)
    assert any("WS LLM stream started session=session-1" in m for m in messages)
    assert any("WS TTS sentence session=session-1" in m and "Refunds take 5-7 business days." in m for m in messages)
    assert any("WS sentence sent session=session-1" in m and "Refunds take 5-7 business days." in m for m in messages)
    assert any("WS response ready session=session-1" in m for m in messages)

    mock_create_session.assert_called_once_with(
        persona_id="default",
        user_id=ANY,
        session_id="session-1",
    )
    mock_manager.send_bytes.assert_called_once_with("session-1", b"tts-audio")
    mock_manager.send_json.assert_any_call("session-1", {
        "type": "sentence_end",
        "text": "Refunds take 5-7 business days.",
        "index": 0,
    })


@pytest.mark.asyncio
async def test_pipeline_empty_transcript():
    mock_ws = AsyncMock(spec=WebSocket)

    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.services.voice_pipeline.manager") as mock_vp_manager, \
         patch("app.services.tts.manager") as mock_tts_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock), \
         patch("app.websocket.handler.VADBuffer") as mock_vad_cls, \
         patch("app.websocket.handler.pcm_to_wav") as mock_convert, \
         patch("app.websocket.handler.decode_to_pcm") as mock_decode, \
         patch("app.websocket.handler.transcribe_audio") as mock_stt, \
         patch("app.websocket.handler.save_session_recording", new_callable=AsyncMock), \
         patch("app.services.voice_pipeline.analyze_sentiment", new_callable=AsyncMock) as mock_analyze_sentiment, \
         patch("app.services.voice_pipeline.save_turn", new_callable=AsyncMock), \
         patch("app.websocket.handler.get_persona_voice_id", new_callable=AsyncMock) as mock_get_voice, \
         patch("app.websocket.handler._get_default_persona_id", new_callable=AsyncMock) as mock_get_default_persona, \
         patch("app.websocket.handler._load_session", new_callable=AsyncMock) as mock_load_session:
        mock_get_voice.return_value = "en-IN-NeerjaNeural"
        mock_get_default_persona.return_value = "default"
        mock_load_session.return_value = None

        mock_vad = MagicMock()
        mock_vad.process = MagicMock(return_value=(b"audio", True))
        mock_vad_cls.return_value = mock_vad

        mock_decode.return_value = _make_pcm_chunk(250)
        mock_convert.return_value = b"wav-audio"
        mock_stt.return_value = ""
        mock_analyze_sentiment.return_value = "neutral"

        mock_create_session.return_value = "db-session-1"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.send_bytes = AsyncMock()

        mock_ws.receive = AsyncMock(side_effect=[
            {"bytes": _make_pcm_chunk(250)},
            WebSocketDisconnect(),
        ])

        await ws_router.routes[0].endpoint(mock_ws, "session-1")

    logs = _get_session_logs("session-1")
    messages = [entry["msg"] for entry in logs]
    assert any("WS empty transcript" in m for m in messages)
    mock_manager.send_json.assert_any_call("session-1", {"type": "error", "message": "empty_transcript"})


@pytest.mark.asyncio
async def test_pipeline_auth_flow():
    mock_ws = AsyncMock(spec=WebSocket)

    with patch("app.websocket.handler.manager") as mock_manager, \
         patch("app.websocket.handler.create_session", new_callable=AsyncMock) as mock_create_session, \
         patch("app.websocket.handler.end_session", new_callable=AsyncMock) as mock_end_session, \
         patch("app.websocket.handler.get_persona_voice_id", new_callable=AsyncMock) as mock_get_voice, \
         patch("app.websocket.handler._get_default_persona_id", new_callable=AsyncMock) as mock_get_default_persona, \
         patch("app.websocket.handler._load_session", new_callable=AsyncMock) as mock_load_session:
        mock_get_voice.return_value = "en-IN-NeerjaNeural"
        mock_get_default_persona.return_value = "default"
        mock_load_session.return_value = None

        mock_create_session.return_value = "session-1"
        mock_manager.connect = AsyncMock()
        mock_manager.disconnect = MagicMock()
        mock_manager.send_json = AsyncMock()
        mock_manager.send_bytes = AsyncMock()

        mock_ws.receive = AsyncMock(side_effect=[
            {"text": '{"type": "auth", "persona_id": "p1", "voice_id": "v1"}'},
            WebSocketDisconnect(),
        ])

        await ws_router.routes[0].endpoint(mock_ws, "session-1")

    logs = _get_session_logs("session-1")
    messages = [entry["msg"] for entry in logs]
    assert any("WS authenticated" in m for m in messages)
    assert any("WS disconnected" in m for m in messages)
    mock_create_session.assert_called_once_with(
        persona_id="default",
        user_id=ANY,
        session_id="session-1",
    )
