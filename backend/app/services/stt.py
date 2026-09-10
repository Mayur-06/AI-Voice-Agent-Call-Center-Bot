import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# One pooled client for the process: a new AsyncClient per request forces a
# fresh TCP + TLS handshake to Groq on every single turn.
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def transcribe_audio(audio_bytes: bytes, language: str = "en") -> str:
    client = get_client()
    files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
    data = {
        "model": "whisper-large-v3-turbo",
        "language": language,
        "response_format": "json",
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
    response = await client.post(GROQ_STT_URL, files=files, data=data, headers=headers)
    response.raise_for_status()
    result = response.json()
    return result.get("text", "")


def is_noisy_transcription(text: str) -> bool:
    """Reject transcripts that are almost certainly noise.

    Digits count as content: in a call centre, "25", "order 4471" and
    "it's $19.99" are the most important things a caller says.
    """
    if not text:
        return True
    stripped = text.strip()
    if len(stripped) < 2:
        # A lone digit is a legitimate answer; a lone letter or symbol is not.
        return not stripped.isdigit()
    content = sum(c.isalnum() for c in stripped)
    # Only apply the ratio heuristic to longer strings - short numeric replies
    # ("25.", "no.") are legitimately punctuation-heavy.
    if len(stripped) > 10 and content / len(stripped) < 0.5:
        return True
    if content == 0:
        return True
    return False
