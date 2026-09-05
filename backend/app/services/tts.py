import asyncio
import io
import logging
import re
import time
from datetime import datetime, timezone
from typing import AsyncIterable, Tuple

from edge_tts import Communicate
from app.config import settings
from app.models.database import get_supabase, run_supabase
from app.websocket.manager import manager, _append_log

logger = logging.getLogger(__name__)

_MARKDOWN_PATTERN = re.compile(
    r"(\*\*|__)(.*?)\1|"          # bold
    r"(?<!\\)(\*|_)(.*?)\3|"      # italic
    r"`{1,3}([^`]+)`{1,3}|"       # code
    r"!\[[^\]]*\]\([^)]*\)|"      # images
    r"\[([^\]]+)\]\([^)]*\)|"     # links
    r"^\s*[-*]\s+|"               # list bullets
    r"^\s*#{1,6}\s+|"             # headings
    r"^\s*>\s+|"                  # blockquotes
    r"^\s*(\d+\.\s*)|"            # ordered lists
    r"---|___|\*\*\*",            # horizontal rules
    re.MULTILINE,
)


def strip_markdown(text: str) -> str:
    cleaned = _MARKDOWN_PATTERN.sub(
        lambda m: m.group(2) or m.group(4) or m.group(5) or m.group(6) or "", text
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


async def get_persona_voice_id(persona_id: str) -> str:
    client = get_supabase()
    try:
        res = await run_supabase(lambda: client.table("personas").select("voice_id").eq("id", persona_id).limit(1).execute())
        if res.data:
            return res.data[0]["voice_id"]
    except Exception:
        pass
    return "en-IN-NeerjaNeural"


async def synthesize_speech(text: str, voice_id: str) -> bytes:
    communicate = Communicate(text=text, voice=voice_id)
    audio_buffer = io.BytesIO()
    async for chunk in _stream_audio_chunks(communicate):
        audio_buffer.write(chunk)
    return audio_buffer.getvalue()


async def synthesize_speech_stream(text: str, voice_id: str):
    communicate = Communicate(text=text, voice=voice_id)
    async for chunk in _stream_audio_chunks(communicate):
        yield chunk


async def stream_sentences(
    session_id: str,
    sentences: AsyncIterable[Tuple[str, int]],
    voice_id: str,
) -> Tuple[int, int | None]:
    if not isinstance(voice_id, str) or not voice_id:
        voice_id = "en-IN-NeerjaNeural"
    sentences_sent = 0
    first_sentence_queued_time: float | None = None
    first_audio_chunk_time: float | None = None

    async for sentence, idx in sentences:
        if first_sentence_queued_time is None:
            first_sentence_queued_time = time.perf_counter()

        seg_start_ms = int((time.perf_counter() - first_sentence_queued_time) * 1000) if first_sentence_queued_time else 0
        manager.start_ai_segment(session_id, seg_start_ms)
        await manager.send_json(session_id, {"type": "status", "message": "speaking", "sentence_index": idx})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS TTS sentence session={session_id} index={idx} text={sentence}"})
        audio_buffer = bytearray()
        first_chunk_received = False
        try:
            spoken_text = await asyncio.to_thread(strip_markdown, sentence)
            async for audio_chunk in synthesize_speech_stream(spoken_text, voice_id):
                if not first_chunk_received:
                    first_audio_chunk_time = time.perf_counter()
                    first_chunk_received = True
                audio_buffer.extend(audio_chunk)
                manager.append_ai_audio(session_id, audio_chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await manager.send_json(session_id, {"type": "error", "message": f"tts_failed:{exc}"})
            await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "error", "msg": f"WS TTS failed session={session_id} sentence={idx} error={exc}"})
        if audio_buffer:
            await manager.send_bytes(session_id, bytes(audio_buffer))
        seg_end_ms = int((time.perf_counter() - first_sentence_queued_time) * 1000) if first_sentence_queued_time else seg_start_ms
        manager.finish_ai_segment(session_id, seg_end_ms)
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
