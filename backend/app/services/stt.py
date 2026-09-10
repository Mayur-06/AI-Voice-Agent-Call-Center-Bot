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


# Whisper answers silence with a small, very consistent set of stock phrases.
# In one call where the user said nothing these appeared 20+ times and the
# agent replied to every one of them.
#
# Several are also things a caller genuinely says ("thank you", "okay",
# "hello"), so the phrase alone is not enough to reject on - it is only
# treated as a hallucination when the clip contained too little voiced audio
# to plausibly carry it. See VOICED_MS_FOR_STOCK_PHRASE.
_WHISPER_STOCK_PHRASES = {
    "thank you", "thanks", "thank you very much", "thanks for watching",
    "thank you for watching", "please subscribe", "subscribe", "the end",
    "music", "applause", "silence", "you", "uh", "um", "hmm", "mm",
    "so", "oh", "okay", "ok", "yeah", "bye", "bye bye", "goodbye",
    "i'm sorry", "sorry", "i'm going to go", "you're welcome", "hello",
}

# A stock phrase needs at least this much voiced audio behind it to be
# believed. The VAD's energy gate (MIN_SPEECH_RMS) now stops silence and room
# tone reaching the transcriber at all, so this filter no longer carries that
# job alone and can afford to be generous - low enough that a caller who
# genuinely just says "Thank you." is still heard.
VOICED_MS_FOR_STOCK_PHRASE = 350


def is_hallucinated_silence(text: str, voiced_ms: int | None = None) -> bool:
    """True if this looks like Whisper inventing words from silence."""
    cleaned = " ".join(text.strip().strip(".,!?-—– ").lower().split())
    if not cleaned:
        return True
    if cleaned not in _WHISPER_STOCK_PHRASES:
        return False
    # Unknown duration: give the caller the benefit of the doubt.
    if voiced_ms is None:
        return False
    return voiced_ms < VOICED_MS_FOR_STOCK_PHRASE


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
