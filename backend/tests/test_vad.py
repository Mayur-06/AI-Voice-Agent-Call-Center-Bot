import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import struct
import time
import pytest
from app.services.vad import VADBuffer


def _make_frame(value: bool, frame_size: int = 1024) -> bytes:
    sample = 0x7FFF if value else 0x0000
    return struct.pack(f"<{frame_size // 2}h", *(sample for _ in range(frame_size // 2)))


@pytest.fixture
def vad_buffer():
    return VADBuffer(sample_rate=16000, frame_duration_ms=30)


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


def test_vad_full_turn_boundary_speech_then_silence(vad_buffer):
    vad_buffer._is_speech = lambda frame: True
    vad_buffer.frame_duration_ms = 30

    import app.services.vad as vad_module
    vad_module.settings.silence_threshold_ms = 128

    try:
        speech_frames = [_make_frame(True, 960) for _ in range(4)]
        silence_frames = [_make_frame(False, 960) for _ in range(10)]

        result = None
        for f in speech_frames:
            result, triggered, onset, end = vad_buffer.process(f)
            assert result is None

        for f in silence_frames:
            result, triggered, onset, end = vad_buffer.process(f)
            if result is not None:
                break

        assert result is not None
        assert len(result) == 4 * 960
        assert triggered is True
        assert onset is not None
        assert end is not None
    finally:
        vad_module.settings.silence_threshold_ms = 800


def test_vad_ignores_short_silence(vad_buffer):
    vad_buffer._is_speech = lambda frame: True
    vad_buffer.frame_duration_ms = 30

    import app.services.vad as vad_module
    original_threshold = vad_module.settings.silence_threshold_ms
    vad_module.settings.silence_threshold_ms = 200

    try:
        speech_frames = [_make_frame(True) for _ in range(3)]
        short_silence = [_make_frame(False) for _ in range(2)]
        resume_speech = [_make_frame(True) for _ in range(2)]

        for f in speech_frames:
            vad_buffer.process(f)

        for f in short_silence:
            result, triggered, onset, end = vad_buffer.process(f)
            assert result is None

        for f in resume_speech:
            result, triggered, onset, end = vad_buffer.process(f)
            assert result is None

        assert vad_buffer.triggered is True
    finally:
        vad_module.settings.silence_threshold_ms = original_threshold


def test_vad_does_not_trigger_on_silence(vad_buffer):
    vad_buffer._is_speech = lambda frame: False
    frame = _make_frame(False)
    result, triggered, onset, end = vad_buffer.process(frame)
    assert result is None
    assert vad_buffer.triggered is False
    assert onset is None
    assert end is None


def test_vad_flush_returns_buffered_speech(vad_buffer):
    vad_buffer._is_speech = lambda frame: True
    frames = [_make_frame(True) for _ in range(3)]
    for f in frames:
        vad_buffer.process(f)
    assert vad_buffer.triggered is True
    audio = vad_buffer.flush()
    assert audio is not None
    assert len(audio) == 3 * 1024
    assert vad_buffer.triggered is False


def test_vad_flush_empty_returns_none(vad_buffer):
    audio = vad_buffer.flush()
    assert audio is None


def test_vad_process_bytes_accumulates(vad_buffer):
    vad_buffer._is_speech = lambda frame: True
    vad_buffer.frame_duration_ms = 30

    import app.services.vad as vad_module
    vad_module.settings.silence_threshold_ms = 128

    try:
        data = b"".join([_make_frame(True, 960) for _ in range(4)] + [_make_frame(False, 960) for _ in range(10)])
        result, triggered, onset, end = vad_buffer.process_bytes(data, frame_size=960)
        assert result is not None
        assert len(result) == 4 * 960
    finally:
        vad_module.settings.silence_threshold_ms = 800
