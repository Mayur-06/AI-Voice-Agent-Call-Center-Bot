import io
import logging
from edge_tts import Communicate
from app.config import settings

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


async def _stream_audio_chunks(communicate):
    try:
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                yield chunk.get("data", b"")
    except Exception as exc:
        logger.exception("Edge TTS synthesis failed: %s", exc)
        raise RuntimeError(f"Edge TTS synthesis failed: {exc}") from exc
