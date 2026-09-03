import sys
import os
import io
import wave
import time
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from app.config import settings
from app.services.vad import VADBuffer
from app.services.audio_processor import decode_to_pcm, pcm_to_wav
from app.services.stt import transcribe_audio


TEST_AUDIO_PATH = os.path.join(os.path.dirname(__file__), "recordings", "WhatsApp Ptt 2026-08-29 at 17.07.17.wav")


def read_wav(path: str) -> tuple[bytes, int, int, int]:
    with wave.open(path, "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    return frames, sample_rate, channels, sample_width


def pcm_to_frames(pcm: bytes, frame_size: int) -> list[bytes]:
    frames = []
    for i in range(0, len(pcm), frame_size):
        frame = pcm[i : i + frame_size]
        if len(frame) == frame_size:
            frames.append(frame)
    return frames


async def main():
    print("=" * 60)
    print("AUDIO INPUT + VAD TEST")
    print("=" * 60)

    if not os.path.exists(TEST_AUDIO_PATH):
        print(f"ERROR: Test audio not found at {TEST_AUDIO_PATH}")
        return

    with open(TEST_AUDIO_PATH, "rb") as f:
        raw_bytes = f.read()

    print(f"File: {os.path.basename(TEST_AUDIO_PATH)}")
    print(f"  raw_bytes={len(raw_bytes)}")

    pcm, sr, ch, sw = read_wav(TEST_AUDIO_PATH)
    duration_ms = int((len(pcm) / (sr * ch * sw)) * 1000)

    print(f"  sample_rate={sr} (target={settings.audio_sample_rate})")
    print(f"  channels={ch} (target=1)")
    print(f"  sample_width={sw} (target=2)")
    print(f"  duration_ms={duration_ms}")

    if sr != settings.audio_sample_rate or ch != 1 or sw != 2:
        print(f"\nResampling to {settings.audio_sample_rate}Hz mono 16-bit...")
        pcm = decode_to_pcm(raw_bytes, sample_rate=settings.audio_sample_rate)
        duration_ms = int((len(pcm) / (settings.audio_sample_rate * 2)) * 1000)
        print(f"  resampled bytes={len(pcm)}, duration_ms={duration_ms}")

    frame_duration_ms = 30
    frame_size = int(settings.audio_sample_rate * 2 * (frame_duration_ms / 1000))
    frames = pcm_to_frames(pcm, frame_size)
    print(f"\nVAD config:")
    print(f"  aggressiveness={settings.vad_aggressiveness}")
    print(f"  silence_threshold_ms={settings.silence_threshold_ms}")
    print(f"  frame_duration_ms={frame_duration_ms}")
    print(f"  frame_size={frame_size} bytes")
    print(f"  total_frames={len(frames)}")

    vad = VADBuffer(sample_rate=settings.audio_sample_rate, frame_duration_ms=frame_duration_ms)

    print("\nRunning VAD...")
    speech_segments = []
    speech_started_at_ms = None
    speech_frames_count = 0
    vad_frames_count = 0

    for idx, frame in enumerate(frames):
        vad_frames_count += 1
        frame_audio, speech_ended = vad.process(frame)

        if vad.triggered and speech_started_at_ms is None:
            speech_started_at_ms = idx * frame_duration_ms
            print(f"  [SPEECH START] at {speech_started_at_ms}ms")

        if speech_ended and frame_audio:
            speech_ended_at_ms = idx * frame_duration_ms
            segment_duration_ms = speech_ended_at_ms - speech_started_at_ms
            print(f"  [SPEECH END] at {speech_ended_at_ms}ms (duration={segment_duration_ms}ms, audio_bytes={len(frame_audio)})")
            speech_segments.append((speech_started_at_ms, speech_ended_at_ms, frame_audio))
            speech_started_at_ms = None

    if vad.triggered:
        flushed = vad.flush()
        if flushed:
            end_ms = len(frames) * frame_duration_ms
            print(f"  [SPEECH END - FLUSHED] at {end_ms}ms (audio_bytes={len(flushed)})")
            speech_segments.append((speech_started_at_ms or 0, end_ms, flushed))

    total_speech_ms = sum(seg[1] - seg[0] for seg in speech_segments)
    total_speech_bytes = sum(len(seg[2]) for seg in speech_segments)

    print(f"\nResults:")
    print(f"  segments_found={len(speech_segments)}")
    print(f"  total_speech_ms={total_speech_ms}")
    print(f"  total_speech_bytes={total_speech_bytes}")
    print(f"  file_duration_ms={duration_ms}")

    if not speech_segments:
        print("\nWARNING: No speech detected by VAD. Possible causes:")
        print("  - VAD aggressiveness too high")
        print("  - silence_threshold_ms too short")
        print("  - Audio format mismatch")
        print("  - No actual speech in file")
        return

    print("\nTranscribing first speech segment via STT...")
    first_segment_audio = speech_segments[0][2]
    wav_audio = pcm_to_wav(first_segment_audio, sample_rate=settings.audio_sample_rate)
    try:
        stt_start = time.perf_counter()
        user_text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=30)
        stt_latency_ms = int((time.perf_counter() - stt_start) * 1000)
        print(f"  transcript=\"{user_text}\"")
        print(f"  stt_latency_ms={stt_latency_ms}")
    except Exception as exc:
        print(f"  STT failed: {exc}")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
