import io
import queue
import struct
import av
import numpy as np


def _open_container(audio_bytes: bytes):
    return av.open(io.BytesIO(audio_bytes))


class QueueReader(io.RawIOBase):
    """File-like adapter so PyAV can decode an MP3 that is still arriving.

    Deliberately does NOT implement seek(): PyAV then treats the source as a
    non-seekable stream and decodes progressively instead of probing the whole
    file first.
    """

    def __init__(self, chunk_queue: "queue.Queue[bytes | None]"):
        self._queue = chunk_queue
        self._buf = b""
        self._eof = False

    def readable(self) -> bool:
        return True

    def readinto(self, target) -> int:
        wanted = len(target)
        while len(self._buf) < wanted and not self._eof:
            chunk = self._queue.get()
            if chunk is None:
                self._eof = True
                break
            self._buf += chunk
        take = min(wanted, len(self._buf))
        target[:take] = self._buf[:take]
        self._buf = self._buf[take:]
        return take


def iter_pcm_from_stream(reader, sample_rate: int = 16000, min_chunk_bytes: int = 3200):
    """Decode a streaming audio source to mono s16 PCM, yielding as it goes."""
    container = av.open(reader)
    try:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise RuntimeError("No audio stream found in container")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
        pending = bytearray()
        for packet in container.demux(stream):
            for frame in packet.decode():
                resampled = resampler.resample(frame)
                frames = resampled if isinstance(resampled, list) else [resampled]
                for f in frames:
                    if f is not None:
                        pending.extend(f.to_ndarray().tobytes())
                if len(pending) >= min_chunk_bytes:
                    yield bytes(pending)
                    pending.clear()
        if pending:
            yield bytes(pending)
    finally:
        container.close()


def decode_to_pcm(audio_bytes: bytes, sample_rate: int = 16000) -> bytes:
    try:
        container = _open_container(audio_bytes)
    except Exception as exc:
        raise RuntimeError(f"Failed to open audio container: {exc}") from exc

    audio_streams = [s for s in container.streams if s.type == "audio"]
    if not audio_streams:
        container.close()
        raise RuntimeError("No audio stream found in container")

    stream = audio_streams[0]
    resampler = av.AudioResampler(
        format="s16",
        layout="mono",
        rate=sample_rate,
    )
    frames = []
    for packet in container.demux(stream):
        for frame in packet.decode():
            resampled = resampler.resample(frame)
            if isinstance(resampled, list):
                for f in resampled:
                    frames.append(f.to_ndarray().tobytes())
            else:
                frames.append(resampled.to_ndarray().tobytes())
    container.close()
    return b"".join(frames)


def convert_to_wav(audio_bytes: bytes, sample_rate: int = 16000) -> bytes:
    pcm = decode_to_pcm(audio_bytes, sample_rate=sample_rate)
    byte_rate = sample_rate * 1 * 2
    block_align = 1 * 2
    data_size = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        byte_rate,
        block_align,
        16,
        b"data",
        data_size,
    )
    return header + pcm


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    data_size = len(pcm_bytes)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,
        b"data",
        data_size,
    )
    return header + pcm_bytes


def strip_wav_header(data: bytes) -> bytes:
    """Return the PCM payload of a WAV, or the input if it is already raw.

    TTS chunks arrive as complete WAVs. Appending them straight into the
    recording buffer embedded a 44-byte RIFF header as audio, producing an
    audible click at every chunk boundary in the saved call.
    """
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return data
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        size = int.from_bytes(data[pos + 4:pos + 8], "little")
        pos += 8
        if chunk_id == b"data":
            return data[pos:pos + size] if size else data[pos:]
        pos += size + (size & 1)
    return b""


def get_duration_ms(audio_bytes: bytes) -> int:
    try:
        container = _open_container(audio_bytes)
    except Exception as exc:
        raise RuntimeError(f"Failed to open audio container: {exc}") from exc

    stream = next((s for s in container.streams if s.type == "audio"), None)
    if stream is None:
        container.close()
        raise RuntimeError("No audio stream found in container")

    duration = 0.0
    if stream.duration and stream.time_base:
        duration = float(stream.duration * stream.time_base)
    elif stream.container.duration is not None:
        duration = float(stream.container.duration) / 1_000_000.0
    container.close()
    return int(duration * 1000)


def _pcm_duration_ms(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> int:
    frame_bytes = channels * sample_width
    total_frames = len(pcm_bytes) // frame_bytes
    return int((total_frames / sample_rate) * 1000)


def compose_call_recording(user_pcm: bytes, ai_segments: list[dict], sample_rate: int = 16000) -> bytes:
    if not user_pcm and not ai_segments:
        return b""

    if not user_pcm:
        combined = bytearray()
        for seg in sorted(ai_segments, key=lambda s: s.get("start_ms", 0)):
            gap_samples = int(((seg.get("start_ms", 0) - (seg.get("prev_end_ms", 0))) / 1000.0) * sample_rate) * 2
            combined.extend(b"\x00" * max(gap_samples, 0))
            combined.extend(seg.get("pcm", b""))
        return pcm_to_wav(bytes(combined), sample_rate=sample_rate)

    user_duration_ms = _pcm_duration_ms(user_pcm, sample_rate=sample_rate)
    total_user_ms = user_duration_ms

    timeline: list[tuple[int, bytes, str]] = []
    timeline.append((0, user_pcm, "user"))

    ai_offset_ms = 0
    prev_end_ms = 0
    for seg in sorted(ai_segments, key=lambda s: s.get("start_ms", 0)):
        start_ms = seg.get("start_ms", prev_end_ms)
        if start_ms < prev_end_ms:
            start_ms = prev_end_ms
        gap_ms = start_ms - prev_end_ms
        if gap_ms > 0:
            ai_offset_ms += gap_ms
        timeline.append((ai_offset_ms, seg.get("pcm", b""), "ai"))
        prev_end_ms = start_ms + seg.get("duration_ms", 0)

    max_end_ms = max(total_user_ms, prev_end_ms) if ai_segments else total_user_ms
    total_samples = int((max_end_ms / 1000.0) * sample_rate) * 2
    if total_samples <= 0:
        return pcm_to_wav(user_pcm, sample_rate=sample_rate)

    # Sum into int32 then clip, so overlapping speakers mix instead of one
    # erasing the other. The previous per-sample Python loop assigned rather
    # than added, and ran ~4.8M iterations for a five-minute call.
    total_frames = total_samples // 2
    accumulator = np.zeros(total_frames, dtype=np.int32)
    for offset_ms, pcm, _speaker in timeline:
        if not pcm:
            continue
        samples = np.frombuffer(pcm[: len(pcm) - (len(pcm) % 2)], dtype="<i2")
        start = int((offset_ms / 1000.0) * sample_rate)
        if start < 0 or start >= total_frames:
            continue
        end = min(start + samples.size, total_frames)
        if end > start:
            accumulator[start:end] += samples[: end - start]

    mixed = np.clip(accumulator, -32768, 32767).astype("<i2").tobytes()
    return pcm_to_wav(mixed, sample_rate=sample_rate)


async def save_session_recording(session_id: str, audio_buffer: bytes):
    try:
        # compose_call_recording() already returns a complete WAV. Wrapping it
        # again embedded a second 44-byte RIFF header inside the audio data,
        # producing an audible click at the start of every saved call and a
        # file whose declared sizes did not match its contents.
        if audio_buffer[:4] == b"RIFF" and audio_buffer[8:12] == b"WAVE":
            wav_bytes = audio_buffer
        else:
            wav_bytes = pcm_to_wav(audio_buffer)
    except Exception as exc:
        raise RuntimeError(f"Failed to encode session recording to WAV: {exc}") from exc

    from app.services.storage import upload_recording
    storage_path = await upload_recording(wav_bytes, session_id)
    return storage_path
