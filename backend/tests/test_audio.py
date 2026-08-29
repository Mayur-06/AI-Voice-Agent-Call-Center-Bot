import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import struct
import pytest
from app.services.audio import convert_to_wav, get_duration_ms


def _make_wav(sample_rate: int = 16000, duration_ms: int = 100) -> bytes:
    num_samples = int(sample_rate * duration_ms / 1000)
    data_size = num_samples * 2
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
        sample_rate * 2,
        2,
        16,
        b"data",
        data_size,
    )
    samples = bytes([0x00, 0x80] * num_samples)
    return header + samples


def test_convert_to_wav():
    wav_in = _make_wav()
    wav_data = convert_to_wav(wav_in, sample_rate=16000)
    assert isinstance(wav_data, bytes)
    assert len(wav_data) > 0
    assert wav_data[:4] == b"RIFF"


def test_get_duration_ms():
    wav_in = _make_wav(duration_ms=100)
    duration = get_duration_ms(wav_in)
    assert isinstance(duration, int)
    assert duration >= 100
