import io
import logging
import re

from edge_tts import Communicate
from app.models.database import get_supabase, run_supabase

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


async def _stream_audio_chunks(communicate):
    try:
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                yield chunk.get("data", b"")
    except Exception as exc:
        logger.exception("Edge TTS synthesis failed: %s", exc)
        raise RuntimeError(f"Edge TTS synthesis failed: {exc}") from exc
