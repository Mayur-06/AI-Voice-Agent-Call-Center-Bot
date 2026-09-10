import collections
import logging
import time
import webrtcvad
from app.config import settings

logger = logging.getLogger(__name__)

# Frames of audio kept before speech is detected, so that soft consonants at
# the start of a word ("fifty", "seven") are not clipped off.
PRE_ROLL_MS = 300


class VADBuffer:
    def __init__(self, sample_rate: int, frame_duration_ms: int = 30):
        if sample_rate not in (8000, 16000, 32000, 48000):
            raise ValueError("WebRTC VAD supports 8, 16, 32, or 48 kHz audio")
        if frame_duration_ms not in (10, 20, 30):
            raise ValueError("WebRTC VAD requires 10, 20, or 30 ms frames")
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self._vad = webrtcvad.Vad(settings.vad_aggressiveness)
        # Contiguous audio for the current utterance, including internal pauses.
        self.buffer: collections.deque = collections.deque()
        self.triggered = False
        # Retained only so callers/tests can inspect how much was voiced.
        self.speech_frames: collections.deque = collections.deque()
        self._pre_roll: collections.deque = collections.deque(
            maxlen=max(1, PRE_ROLL_MS // frame_duration_ms)
        )
        self._pending_pcm: bytearray = bytearray()
        self._speech_onset: float | None = None
        # Consecutive trailing silence, reset by every voiced frame.
        self._trailing_silence_ms = 0
        # Set for exactly one process() call, when speech first starts.
        self.just_triggered = False
        # Latched on trigger, cleared by the consumer. Lets the pipeline fire
        # barge-in the moment the user starts speaking rather than waiting for
        # them to finish.
        self.onset_pending = False

    def _is_speech(self, frame: bytes) -> bool:
        try:
            return self._vad.is_speech(frame, self.sample_rate)
        except Exception as exc:
            logger.debug("WebRTC VAD frame error: %s", exc)
            return False

    def process(self, frame: bytes) -> tuple[bytes | None, bool, float | None, float | None]:
        self.just_triggered = False
        if len(frame) % 2 != 0:
            return None, False, None, None
        is_speech = self._is_speech(frame)
        now = time.perf_counter()

        if not self.triggered:
            if is_speech:
                self.triggered = True
                self.just_triggered = True
                self.onset_pending = True
                # Prepend the pre-roll so the onset of the word survives.
                self.buffer.clear()
                self.speech_frames.clear()
                self.buffer.extend(self._pre_roll)
                self._pre_roll.clear()
                self.buffer.append(frame)
                self.speech_frames.append(frame)
                self._trailing_silence_ms = 0
                self._speech_onset = now
                return None, False, self._speech_onset, None
            self._pre_roll.append(frame)
            return None, False, None, None

        # Triggered: keep every frame so the audio handed to STT is contiguous.
        self.buffer.append(frame)
        if is_speech:
            self.speech_frames.append(frame)
            self._trailing_silence_ms = 0
            return None, False, self._speech_onset, None

        self._trailing_silence_ms += self.frame_duration_ms
        if self._trailing_silence_ms >= settings.silence_threshold_ms:
            audio = b"".join(self.buffer)
            speech_end = now
            speech_onset = self._speech_onset
            self.reset()
            return audio, True, speech_onset, speech_end
        return None, False, self._speech_onset, None

    def process_bytes(self, data: bytes, frame_size: int) -> tuple[bytes | None, bool, float | None, float | None]:
        self._pending_pcm.extend(data)
        last_result: tuple[bytes | None, bool, float | None, float | None] = (None, False, None, None)
        while len(self._pending_pcm) >= frame_size:
            frame = bytes(self._pending_pcm[:frame_size])
            del self._pending_pcm[:frame_size]
            try:
                last_result = self.process(frame)
            except Exception as exc:
                logger.debug("VAD process error: %s", exc)
                last_result = (None, False, None, None)
            if last_result[0] is not None:
                break
        return last_result

    def reset(self):
        self.triggered = False
        self.just_triggered = False
        self.onset_pending = False
        self.buffer.clear()
        self.speech_frames.clear()
        self._pre_roll.clear()
        self._pending_pcm.clear()
        self._speech_onset = None
        self._trailing_silence_ms = 0

    def flush(self) -> bytes | None:
        if not self.buffer:
            self.reset()
            return None
        audio = b"".join(self.buffer)
        self.reset()
        return audio
