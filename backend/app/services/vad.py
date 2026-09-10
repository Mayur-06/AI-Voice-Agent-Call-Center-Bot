import collections
import logging
import time
import webrtcvad
from app.config import settings

logger = logging.getLogger(__name__)


class VADBuffer:
    def __init__(self, sample_rate: int, frame_duration_ms: int = 30):
        if sample_rate not in (8000, 16000, 32000, 48000):
            raise ValueError("WebRTC VAD supports 8, 16, 32, or 48 kHz audio")
        if frame_duration_ms not in (10, 20, 30):
            raise ValueError("WebRTC VAD requires 10, 20, or 30 ms frames")
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self._vad = webrtcvad.Vad(settings.vad_aggressiveness)
        self.buffer: collections.deque = collections.deque()
        self.triggered = False
        self.speech_frames: collections.deque = collections.deque()
        self._pending_pcm: bytearray = bytearray()
        self._speech_onset: float | None = None

    def _is_speech(self, frame: bytes) -> bool:
        try:
            return self._vad.is_speech(frame, self.sample_rate)
        except Exception as exc:
            logger.info("WebRTC VAD frame error: %s", exc)
            return False

    def process(self, frame: bytes) -> tuple[bytes | None, bool, float | None, float | None]:
        if len(frame) % 2 != 0:
            return None, False, None, None
        logger.debug("VAD process frame_len=%s triggered=%s", len(frame), self.triggered)
        is_speech = self._is_speech(frame)
        now = time.perf_counter()
        if not self.triggered:
            if is_speech:
                self.triggered = True
                self.buffer.clear()
                self.speech_frames.clear()
                self.buffer.append(frame)
                self.speech_frames.append(frame)
                self._speech_onset = now
                return None, False, self._speech_onset, None
            return None, False, None, None
        else:
            self.buffer.append(frame)
            if is_speech:
                self.speech_frames.append(frame)
                return None, False, self._speech_onset, None
            silence_frames = len(self.buffer) - len(self.speech_frames)
            silence_ms = silence_frames * self.frame_duration_ms
            if silence_ms >= settings.silence_threshold_ms:
                audio = b"".join(self.speech_frames)
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
                logger = __import__('logging').getLogger(__name__)
                logger.debug("Silero VAD process error: %s", exc)
                last_result = (None, False, None, None)
            if last_result[0] is not None:
                break
        return last_result

    def reset(self):
        self.triggered = False
        self.buffer.clear()
        self.speech_frames.clear()
        self._pending_pcm.clear()
        self._speech_onset = None

    def flush(self) -> bytes | None:
        if not self.speech_frames:
            self.reset()
            return None
        audio = b"".join(self.speech_frames)
        self.reset()
        return audio
