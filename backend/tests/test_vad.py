import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import struct
import pytest
from app.services.vad import VADBuffer


def _make_frame(value: bool, frame_size: int = 1024) -> bytes:
    sample = 0x7FFF if value else 0x0000
    return struct.pack(f"<{frame_size // 2}h", *(sample for _ in range(frame_size // 2)))


@pytest.fixture
def vad_buffer():
    return VADBuffer(sample_rate=16000, frame_duration_ms=32)


def test_vad_initial_state(vad_buffer):
    assert vad_buffer.triggered is False
    assert len(vad_buffer.buffer) == 0


def test_vad_speech_onset(vad_buffer):
    vad_buffer._is_speech = lambda frame: True
    frame = _make_frame(True)
    result, triggered, onset, end = vad_buffer.process(frame)
    assert result is None
    assert triggered is False
    assert vad_buffer.triggered is True
    assert onset is not None


def test_vad_reset(vad_buffer):
    vad_buffer.triggered = True
    vad_buffer.buffer.append(b"frame")
    vad_buffer.reset()
    assert vad_buffer.triggered is False
    assert len(vad_buffer.buffer) == 0
