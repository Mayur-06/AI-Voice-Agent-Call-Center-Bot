from pydub import AudioSegment
from io import BytesIO
import struct


def convert_to_wav(audio_bytes: bytes, sample_rate: int = 16000) -> bytes:
    audio = AudioSegment.from_file(BytesIO(audio_bytes))
    audio = audio.set_frame_rate(sample_rate).set_channels(1).set_sample_width(2)
    out = BytesIO()
    audio.export(out, format="wav")
    return out.getvalue()


def get_duration_ms(audio_bytes: bytes) -> int:
    audio = AudioSegment.from_file(BytesIO(audio_bytes))
    return len(audio)


def decode_to_pcm(audio_bytes: bytes, sample_rate: int = 16000) -> bytes:
    audio = AudioSegment.from_file(BytesIO(audio_bytes))
    audio = audio.set_frame_rate(sample_rate).set_channels(1).set_sample_width(2)
    return audio.raw_data


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
