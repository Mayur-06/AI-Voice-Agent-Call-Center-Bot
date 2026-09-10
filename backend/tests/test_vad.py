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


def _content_aware_is_speech(frame: bytes) -> bool:
    """Treat an all-zero frame as silence, anything else as speech."""
    return any(frame)


def test_vad_full_turn_boundary_speech_then_silence(vad_buffer):
    vad_buffer._is_speech = _content_aware_is_speech
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
        # Audio handed to STT is contiguous: the 4 voiced frames plus the
        # trailing silence that closed the turn. It is NOT spliced down to
        # voiced frames only, which would mangle the audio for Whisper.
        assert len(result) >= 4 * 960
        assert len(result) % 960 == 0
        assert triggered is True
        assert onset is not None
        assert end is not None
    finally:
        vad_module.settings.silence_threshold_ms = 800


def test_vad_ignores_short_silence(vad_buffer):
    vad_buffer._is_speech = _content_aware_is_speech
    vad_buffer.frame_duration_ms = 30

    import app.services.vad as vad_module
    original_threshold = vad_module.settings.silence_threshold_ms
    vad_module.settings.silence_threshold_ms = 200

    try:
        speech_frames = [_make_frame(True, 960) for _ in range(3)]
        short_silence = [_make_frame(False, 960) for _ in range(2)]
        resume_speech = [_make_frame(True, 960) for _ in range(2)]

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
    vad_buffer._is_speech = _content_aware_is_speech
    vad_buffer.frame_duration_ms = 30

    import app.services.vad as vad_module
    vad_module.settings.silence_threshold_ms = 128

    try:
        data = b"".join([_make_frame(True, 960) for _ in range(4)] + [_make_frame(False, 960) for _ in range(10)])
        result, triggered, onset, end = vad_buffer.process_bytes(data, frame_size=960)
        assert result is not None
        assert len(result) >= 4 * 960
    finally:
        vad_module.settings.silence_threshold_ms = 800


# --- Regression tests for the endpointing bugs -------------------------------


def test_vad_does_not_end_turn_on_cumulative_internal_pauses(vad_buffer):
    """A speaker pausing between words must not end the turn.

    The old implementation computed silence as
    ``len(buffer) - len(speech_frames)``, i.e. the *cumulative* count of
    unvoiced frames anywhere in the utterance rather than the consecutive
    trailing run. Normal speech has 50-150 ms gaps between words, so after
    roughly six to ten of them the turn was cut off mid-sentence while the
    user was still talking.
    """
    vad_buffer._is_speech = _content_aware_is_speech
    vad_buffer.frame_duration_ms = 30

    import app.services.vad as vad_module
    original = vad_module.settings.silence_threshold_ms
    vad_module.settings.silence_threshold_ms = 300  # 10 frames of 30 ms

    try:
        # "word <pause> word <pause> ..." - 20 short gaps, none long enough
        # to be an endpoint, but 60 unvoiced frames in total (1800 ms), far
        # past the threshold when counted cumulatively.
        for _ in range(20):
            for _ in range(4):
                result, ended, _, _ = vad_buffer.process(_make_frame(True, 960))
                assert result is None, "voiced frame must not end the turn"
            for _ in range(3):  # 90 ms gap - a normal inter-word pause
                result, ended, _, _ = vad_buffer.process(_make_frame(False, 960))
                assert result is None, "an inter-word pause must not end the turn"

        assert vad_buffer.triggered is True, "turn was cut off mid-sentence"

        # Now a genuine trailing pause should close it.
        result = None
        for _ in range(12):
            result, ended, _, _ = vad_buffer.process(_make_frame(False, 960))
            if result is not None:
                break
        assert result is not None, "a real trailing silence must end the turn"
        assert vad_buffer.triggered is False
    finally:
        vad_module.settings.silence_threshold_ms = original


def test_vad_trailing_silence_resets_on_speech(vad_buffer):
    vad_buffer._is_speech = _content_aware_is_speech
    vad_buffer.frame_duration_ms = 30

    import app.services.vad as vad_module
    original = vad_module.settings.silence_threshold_ms
    vad_module.settings.silence_threshold_ms = 150  # 5 frames

    try:
        vad_buffer.process(_make_frame(True, 960))
        for _ in range(4):  # 120 ms - just under the threshold
            vad_buffer.process(_make_frame(False, 960))
        vad_buffer.process(_make_frame(True, 960))  # speech resumes
        assert vad_buffer._trailing_silence_ms == 0
        assert vad_buffer.triggered is True
    finally:
        vad_module.settings.silence_threshold_ms = original


def test_vad_includes_pre_roll_so_word_onset_is_not_clipped(vad_buffer):
    """WebRTC VAD misses the first 30-90 ms of soft consonants.

    Without pre-roll, "fifty" reaches Whisper as "ifty".
    """
    vad_buffer._is_speech = _content_aware_is_speech
    vad_buffer.frame_duration_ms = 30

    # Three frames of near-silence arrive before VAD trips.
    for _ in range(3):
        vad_buffer.process(_make_frame(False, 960))
    assert vad_buffer.triggered is False

    vad_buffer.process(_make_frame(True, 960))
    assert vad_buffer.triggered is True

    audio = vad_buffer.flush()
    assert audio is not None
    # Pre-roll frames are prepended, so more than just the triggering frame.
    assert len(audio) > 960, "speech onset was clipped - no pre-roll retained"
    assert len(audio) == 4 * 960


def test_vad_audio_is_contiguous_not_spliced(vad_buffer):
    """Internal silence must be preserved in the audio sent to STT.

    The old code joined ``speech_frames`` only, splicing out every pause and
    gluing words together at hard boundaries.
    """
    vad_buffer._is_speech = _content_aware_is_speech
    vad_buffer.frame_duration_ms = 30

    import app.services.vad as vad_module
    original = vad_module.settings.silence_threshold_ms
    vad_module.settings.silence_threshold_ms = 300

    try:
        vad_buffer.process(_make_frame(True, 960))
        vad_buffer.process(_make_frame(False, 960))  # internal pause
        vad_buffer.process(_make_frame(True, 960))
        audio = vad_buffer.flush()
        assert audio is not None
        assert len(audio) == 3 * 960, "internal pause was spliced out"
        # The middle frame is still silent in the output.
        assert audio[960:1920] == b"\x00" * 960
    finally:
        vad_module.settings.silence_threshold_ms = original
