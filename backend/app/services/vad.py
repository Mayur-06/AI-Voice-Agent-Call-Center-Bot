import collections
import os
import threading
import torch
from app.config import settings

os.environ.setdefault("TORCH_HUB_TRUSTED_REPOSITORIES", "snakers4/silero-vad")

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model, _ = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    force_reload=False,
                    onnx=False,
                    trust_repo=True,
                )
                _model.eval()
    return _model


class VADBuffer:
    def __init__(self, sample_rate: int, frame_duration_ms: int = 30, threshold: float | None = None):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.threshold = threshold if threshold is not None else settings.vad_threshold
        self.buffer: collections.deque = collections.deque()
        self.triggered = False
        self.speech_frames: collections.deque = collections.deque()
        self._pending_pcm: bytearray = bytearray()

    def _is_speech(self, frame: bytes) -> bool:
        model = _get_model()
        audio = torch.frombuffer(bytearray(frame), dtype=torch.int16).float() / 32768.0
        if audio.dim() == 0:
            return False
        try:
            with torch.no_grad():
                prob = model(audio.unsqueeze(0), self.sample_rate).item()
            logger = __import__('logging').getLogger(__name__)
            logger.debug("Silero VAD prob=%s threshold=%s", round(prob, 3), self.threshold)
            return prob >= self.threshold
        except Exception as exc:
            logger = __import__('logging').getLogger(__name__)
            logger.debug("Silero VAD frame error: %s", exc)
            return False

    def process(self, frame: bytes) -> tuple[bytes | None, bool]:
        if len(frame) % 2 != 0:
            return None, False
        is_speech = self._is_speech(frame)
        if not self.triggered:
            if is_speech:
                self.triggered = True
                self.buffer.clear()
                self.speech_frames.clear()
                self.buffer.append(frame)
                self.speech_frames.append(frame)
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
            except Exception as exc:
                logger = __import__('logging').getLogger(__name__)
                logger.debug("Silero VAD process error: %s", exc)
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
