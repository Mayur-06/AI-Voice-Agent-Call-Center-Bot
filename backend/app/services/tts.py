import io
import logging
from edge_tts import Communicate
from app.config import settings

logger = logging.getLogger(__name__)


async def synthesize_speech(text: str, voice_id: str, output_format: str = "mp3_44100_128") -> bytes:
    communicate = Communicate(text=text, voice=voice_id)
    audio_buffer = io.BytesIO()
    try:
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio_buffer.write(chunk.get("data", b""))
    except Exception as exc:
        logger.exception("Edge TTS synthesis failed: %s", exc)
        raise RuntimeError(f"Edge TTS synthesis failed: {exc}") from exc
    return audio_buffer.getvalue()
