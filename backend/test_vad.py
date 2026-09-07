#!/usr/bin/env python
"""Test VAD with generated sine wave audio."""
import os
import sys
import numpy as np
import torch

# Add backend to path
sys.path.insert(0, r"C:\Users\ktmay\OneDrive\Desktop\AI Voice Agent\backend")

from app.services.vad import VADBuffer, _get_model
from app.config import settings

def generate_sine_wave(duration_s=1.0, frequency=440, sample_rate=16000, amplitude=0.5):
    """Generate a sine wave as int16 PCM bytes."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    wave = amplitude * np.sin(2 * np.pi * frequency * t)
    # Convert to int16
    pcm = (wave * 32767).astype(np.int16)
    return pcm.tobytes()

def test_vad_direct():
    """Test VAD model directly with a sine wave."""
    print("Loading Silero VAD model...")
    model = _get_model()
    print("Model loaded.")
    
    # Generate 1 second of speech-like audio (sine wave)
    audio_bytes = generate_sine_wave(duration_s=1.0, amplitude=0.3)
    print(f"Generated {len(audio_bytes)} bytes of test audio")
    
    # Process in 30ms frames
    frame_duration_ms = 30
    frame_size = int(settings.audio_sample_rate * 2 * (frame_duration_ms / 1000))
    print(f"Frame size: {frame_size} bytes ({frame_duration_ms}ms at 16kHz)")
    
    vad = VADBuffer(sample_rate=settings.audio_sample_rate, threshold=0.1)
    
    for i in range(0, len(audio_bytes), frame_size):
        frame = audio_bytes[i:i+frame_size]
        if len(frame) < frame_size:
            break
        
        # Test _is_speech directly
        audio = torch.frombuffer(bytearray(frame), dtype=torch.int16).float() / 32768.0
        with torch.no_grad():
            prob = model(audio.unsqueeze(0), settings.audio_sample_rate).item()
        
        is_speech = vad._is_speech(frame)
        print(f"Frame {i//frame_size}: prob={prob:.4f}, is_speech={is_speech}, triggered={vad.triggered}")
        
        result = vad.process(frame)
        if result[0] is not None:
            print(f"  -> SPEECH ENDED! audio_bytes={len(result[0])}")

    # Flush any remaining
    flushed = vad.flush()
    if flushed:
        print(f"Flushed {len(flushed)} bytes")

def test_vad_buffer():
    """Test full VADBuffer with process_bytes."""
    print("\n--- Testing VADBuffer.process_bytes ---")
    vad = VADBuffer(sample_rate=settings.audio_sample_rate, threshold=0.1)
    
    # Generate 3 seconds of audio
    audio_bytes = generate_sine_wave(duration_s=3.0, amplitude=0.3)
    frame_duration_ms = 30
    frame_size = int(settings.audio_sample_rate * 2 * (frame_duration_ms / 1000))
    
    result = vad.process_bytes(audio_bytes, frame_size)
    print(f"Result: frame_audio={len(result[0]) if result[0] else 0} bytes, speech_ended={result[1]}, onset={result[2]}, end={result[3]}")
    
    # Test with silence (low amplitude)
    print("\n--- Testing with silence ---")
    silence_bytes = generate_sine_wave(duration_s=1.0, amplitude=0.001)
    vad2 = VADBuffer(sample_rate=settings.audio_sample_rate, threshold=0.1)
    result = vad2.process_bytes(silence_bytes, frame_size)
    print(f"Silence result: frame_audio={len(result[0]) if result[0] else 0} bytes, speech_ended={result[1]}")

if __name__ == "__main__":
    test_vad_direct()
    test_vad_buffer()
    print("\nTest complete.")