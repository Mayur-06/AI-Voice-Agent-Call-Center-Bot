import io
import os
import struct
import av


def _open_container(audio_bytes: bytes):
    return av.open(io.BytesIO(audio_bytes))


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
    user_samples = len(user_pcm) // 2
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

    mixed = bytearray(total_samples)
    for offset_ms, pcm, speaker in timeline:
        offset_samples = int((offset_ms / 1000.0) * sample_rate) * 2
        if offset_samples < 0 or offset_samples >= len(mixed):
            continue
        for i in range(0, len(pcm), 2):
            idx = offset_samples + i
            if idx >= len(mixed):
                break
            sample = int.from_bytes(pcm[i:i+2], byteorder="little", signed=True)
            mixed[idx] = sample & 0xFF
            mixed[idx+1] = (sample >> 8) & 0xFF

    return pcm_to_wav(bytes(mixed), sample_rate=sample_rate)


async def save_session_recording(session_id: str, audio_buffer: bytes):
    try:
        wav_bytes = pcm_to_wav(audio_buffer)
    except Exception as exc:
        raise RuntimeError(f"Failed to encode session recording to WAV: {exc}") from exc

    from app.services.storage import upload_recording
    storage_path = await upload_recording(wav_bytes, session_id)
    return storage_path
