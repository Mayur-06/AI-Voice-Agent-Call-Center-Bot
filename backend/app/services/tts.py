import asyncio
import io
import logging
import time
from datetime import datetime, timezone
from typing import AsyncIterable, Tuple

from edge_tts import Communicate
from app.config import settings
from app.websocket.manager import manager, _append_log

logger = logging.getLogger(__name__)


async def synthesize_speech(text: str, voice_id: str, output_format: str = "mp3_44100_128") -> bytes:
    communicate = Communicate(text=text, voice=voice_id, output_format=output_format)
    audio_buffer = io.BytesIO()
    async for chunk in _stream_audio_chunks(communicate):
        audio_buffer.write(chunk)
    return audio_buffer.getvalue()


async def synthesize_speech_stream(text: str, voice_id: str, output_format: str = "mp3_44100_128"):
    communicate = Communicate(text=text, voice=voice_id, output_format=output_format)
    async for chunk in _stream_audio_chunks(communicate):
        yield chunk


async def stream_sentences(
    session_id: str,
    sentences: AsyncIterable[Tuple[str, int]],
    voice_id: str,
) -> Tuple[int, int | None]:
    sentences_sent = 0
    first_sentence_queued_time: float | None = None
    first_audio_chunk_time: float | None = None

    async for sentence, idx in sentences:
        if first_sentence_queued_time is None:
            first_sentence_queued_time = time.perf_counter()
        await manager.send_json(session_id, {"type": "status", "message": "speaking", "sentence_index": idx})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS TTS sentence session={session_id} index={idx} text={sentence}"})
        audio_buffer = bytearray()
        first_chunk_received = False
        try:
            async for audio_chunk in synthesize_speech_stream(sentence, voice_id):
                if not first_chunk_received:
                    first_audio_chunk_time = time.perf_counter()
                    first_chunk_received = True
                audio_buffer.extend(audio_chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await manager.send_json(session_id, {"type": "error", "message": f"tts_failed:{exc}"})
            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS TTS failed session={session_id} sentence={idx} error={exc}"})
        if audio_buffer:
            await manager.send_bytes(session_id, bytes(audio_buffer))
        await manager.send_json(session_id, {"type": "sentence_end", "text": sentence, "index": idx})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS sentence sent session={session_id} index={idx} text={sentence}"})
        sentences_sent += 1

    tts_first_audio_latency_ms = None
    if first_audio_chunk_time is not None and first_sentence_queued_time is not None:
        tts_first_audio_latency_ms = int((first_audio_chunk_time - first_sentence_queued_time) * 1000)

    return sentences_sent, tts_first_audio_latency_ms


async def _stream_audio_chunks(communicate):
    try:
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                yield chunk.get("data", b"")
    except Exception as exc:
        logger.exception("Edge TTS synthesis failed: %s", exc)
        raise RuntimeError(f"Edge TTS synthesis failed: {exc}") from exc
