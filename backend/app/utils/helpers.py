from pydub import AudioSegment
from io import BytesIO


def ensure_wav_16k(audio_bytes: bytes) -> bytes:
    audio = AudioSegment.from_file(BytesIO(audio_bytes))
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    out = BytesIO()
    audio.export(out, format="wav")
    return out.getvalue()
