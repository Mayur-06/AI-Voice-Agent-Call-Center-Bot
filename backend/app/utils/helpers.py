from app.services.audio_processor import convert_to_wav


def ensure_wav_16k(audio_bytes: bytes) -> bytes:
    return convert_to_wav(audio_bytes, sample_rate=16000)
