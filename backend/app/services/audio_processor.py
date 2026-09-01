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


async def save_session_recording(session_id: str, audio_buffer: bytes):
    os.makedirs("recordings", exist_ok=True)
    file_path = f"recordings/{session_id}.wav"

    try:
        wav_bytes = pcm_to_wav(audio_buffer)
    except Exception as exc:
        raise RuntimeError(f"Failed to encode session recording to WAV: {exc}") from exc

    with open(file_path, "wb") as f:
        f.write(wav_bytes)
    return file_path
