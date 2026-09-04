import collections
import webrtcvad
from app.config import settings


class VADBuffer:
    def __init__(self, sample_rate: int, frame_duration_ms: int = 30):
        self.vad = webrtcvad.Vad(settings.vad_aggressiveness)
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.buffer: collections.deque = collections.deque()
        self.triggered = False
        self.speech_frames: collections.deque = collections.deque()
        self._pending_pcm: bytearray = bytearray()

    def process(self, frame: bytes) -> tuple[bytes | None, bool]:
        is_speech = self.vad.is_speech(frame, self.sample_rate)
        if not self.triggered:
            if is_speech:
                self.triggered = True
                self.buffer.clear()
                self.speech_frames.clear()
                self.buffer.append(frame)
            return None, False
        else:
            self.buffer.append(frame)
            if is_speech:
                self.speech_frames.append(frame)
                return None, False
            silence_frames = len(self.buffer) - len(self.speech_frames)
            silence_ms = silence_frames * self.frame_duration_ms
            if silence_ms >= settings.silence_threshold_ms:
                audio = b"".join(self.speech_frames)
                self.reset()
                return audio, True
            return None, False

    def process_bytes(self, data: bytes, frame_size: int) -> tuple[bytes | None, bool]:
        self._pending_pcm.extend(data)
        last_result: tuple[bytes | None, bool] = (None, False)
        while len(self._pending_pcm) >= frame_size:
            frame = bytes(self._pending_pcm[:frame_size])
            del self._pending_pcm[:frame_size]
            try:
                last_result = self.process(frame)
            except Exception:
                last_result = (None, False)
            if last_result[0] is not None:
                break
        return last_result

    def reset(self):
        self.triggered = False
        self.buffer.clear()
        self.speech_frames.clear()
        self._pending_pcm.clear()

    def flush(self) -> bytes | None:
        if not self.speech_frames:
            self.reset()
            return None
        audio = b"".join(self.speech_frames)
        self.reset()
        return audio
