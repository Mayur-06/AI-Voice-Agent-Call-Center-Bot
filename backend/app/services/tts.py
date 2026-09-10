import asyncio
import contextlib
import io
import logging
import queue
import re

import numpy as np
from edge_tts import Communicate
from app.config import settings
from app.models.database import get_supabase, run_supabase
from app.services.audio_processor import (
    QueueReader,
    convert_to_wav,
    iter_pcm_from_stream,
    pcm_to_wav,
)

logger = logging.getLogger(__name__)

# Edge TTS pads every utterance with roughly 0.26s of leading and 0.86s of
# trailing silence. Synthesising per sentence meant ~1.1s of dead air at every
# sentence boundary, which dominates how sluggish the agent sounds.
_SILENCE_LEVEL = 300           # int16 amplitude treated as silence
_ONSET_PAD_MS = 30             # keep a little before speech starts
_GAP_KEEP_MS = 90              # natural pause left at the end of a sentence


def _first_voiced_index(pcm: bytes) -> int | None:
    samples = np.frombuffer(pcm[: len(pcm) - (len(pcm) % 2)], dtype="<i2")
    voiced = np.flatnonzero(np.abs(samples) > _SILENCE_LEVEL)
    return int(voiced[0]) if voiced.size else None


def _last_voiced_index(pcm: bytes) -> int | None:
    samples = np.frombuffer(pcm[: len(pcm) - (len(pcm) % 2)], dtype="<i2")
    voiced = np.flatnonzero(np.abs(samples) > _SILENCE_LEVEL)
    return int(voiced[-1]) if voiced.size else None


async def _trim_silence(pcm_chunks, sample_rate: int):
    """Strip the leading and trailing silence Edge TTS adds to each utterance.

    Leading silence is dropped as it arrives. Trailing silence is identified
    without holding back a fixed window of audio: a chunk that contains any
    voiced sample is forwarded immediately, and runs of wholly silent chunks
    are buffered instead. A buffered run followed by more speech is an internal
    pause and gets replayed; a run left over at end-of-stream is the trailing
    pad and is dropped down to a short natural gap.

    The previous version held back a fixed 1200ms tail so it could locate the
    end, which added that delay to time-to-first-audio on every sentence.
    """
    bps = sample_rate * 2
    onset_pad = int(_ONSET_PAD_MS / 1000 * bps) & ~1
    keep = int(_GAP_KEEP_MS / 1000 * bps) & ~1

    started = False
    silence_run = bytearray()
    async for chunk in pcm_chunks:
        if not started:
            idx = _first_voiced_index(chunk)
            if idx is None:
                continue  # still in the leading pad
            start = max(0, idx * 2 - onset_pad)
            chunk = chunk[start:]
            started = True
        last = _last_voiced_index(chunk)
        if last is None:
            silence_run.extend(chunk)
            continue
        if silence_run:
            # An internal pause between words: preserve it verbatim.
            yield bytes(silence_run)
            silence_run.clear()
        # Split the chunk at its last voiced sample. The voiced part goes out
        # immediately; the silence after it joins the run, so it is replayed if
        # more speech follows and trimmed if this was the end of the utterance.
        cut = min(len(chunk), last * 2 + 2)
        silence_run.extend(chunk[cut:])
        yield chunk[:cut]

    if started and silence_run:
        remainder = bytes(silence_run[:keep])
        if remainder:
            yield remainder

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
    mp3_bytes = audio_buffer.getvalue()
    # Convert complete MP3 to WAV for reliable browser decoding
    return convert_to_wav(mp3_bytes)


async def synthesize_speech_stream(text: str, voice_id: str):
    """Yield playable audio as it is synthesised.

    Previously this buffered the entire sentence, decoded it, and yielded once
    - so time-to-first-audio was the cost of synthesising the whole sentence.
    Now MP3 chunks are decoded progressively and emitted as small self-
    contained WAVs, which keeps the existing browser decode path unchanged.
    """
    sample_rate = settings.audio_sample_rate
    communicate = Communicate(text=text, voice=voice_id)
    loop = asyncio.get_running_loop()
    mp3_queue: "queue.Queue[bytes | None]" = queue.Queue(maxsize=128)
    pcm_queue: asyncio.Queue = asyncio.Queue()

    def _decode_worker() -> None:
        try:
            for pcm in iter_pcm_from_stream(QueueReader(mp3_queue), sample_rate=sample_rate):
                loop.call_soon_threadsafe(pcm_queue.put_nowait, pcm)
        except BaseException as exc:  # surfaced to the caller below
            loop.call_soon_threadsafe(pcm_queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(pcm_queue.put_nowait, None)

    async def _feed_mp3() -> None:
        try:
            async for chunk in _stream_audio_chunks(communicate):
                if chunk:
                    await asyncio.to_thread(mp3_queue.put, chunk)
        finally:
            await asyncio.to_thread(mp3_queue.put, None)

    decoder = loop.run_in_executor(None, _decode_worker)
    feeder = asyncio.create_task(_feed_mp3())

    async def _raw_pcm():
        while True:
            item = await pcm_queue.get()
            if item is None:
                return
            if isinstance(item, BaseException):
                raise RuntimeError(f"Edge TTS decode failed: {item}") from item
            yield item

    try:
        async for trimmed in _trim_silence(_raw_pcm(), sample_rate):
            yield pcm_to_wav(trimmed, sample_rate=sample_rate)
    finally:
        # On barge-in this generator is closed early: unblock both workers.
        if not feeder.done():
            feeder.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await feeder
        with contextlib.suppress(Exception):
            mp3_queue.put_nowait(None)
        with contextlib.suppress(Exception):
            await decoder


async def _stream_audio_chunks(communicate):
    try:
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                yield chunk.get("data", b"")
    except Exception as exc:
        logger.exception("Edge TTS synthesis failed: %s", exc)
        raise RuntimeError(f"Edge TTS synthesis failed: {exc}") from exc
