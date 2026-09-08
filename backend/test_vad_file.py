#!/usr/bin/env python
"""Test VAD with existing WhatsApp audio file."""
import os
import sys
import torch

# Add backend to path
sys.path.insert(0, r"C:\Users\ktmay\OneDrive\Desktop\AI Voice Agent\backend")

from app.services.vad import VADBuffer, _get_model
from app.config import settings
from app.services.audio_processor import decode_to_pcm

def test_vad_with_file():
    """Test VAD with the WhatsApp audio file."""
    audio_path = r"C:\Users\ktmay\OneDrive\Desktop\AI Voice Agent\backend\recordings\WhatsApp Ptt 2026-08-29 at 17.07.17.wav"
    
    if not os.path.exists(audio_path):
        print(f"File not found: {audio_path}")
        return
    
    print(f"Loading audio file: {audio_path}")
    print(f"File size: {os.path.getsize(audio_path)} bytes")
    
    # Read file as bytes
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    
    # Decode to PCM
    print("Decoding to PCM...")
    pcm_bytes = decode_to_pcm(audio_bytes, settings.audio_sample_rate)
    print(f"PCM size: {len(pcm_bytes)} bytes")
    
    # Test VAD
    print("Loading Silero VAD model...")
    model = _get_model()
    print("Model loaded.")
    
    vad = VADBuffer(sample_rate=settings.audio_sample_rate, threshold=0.1)
    
    frame_duration_ms = 32
    frame_size = int(settings.audio_sample_rate * 2 * (frame_duration_ms / 1000))
    # Silero VAD requires exactly 512 samples for 16kHz
    if settings.audio_sample_rate == 16000:
        frame_size = 1024
    elif settings.audio_sample_rate == 8000:
        frame_size = 512
    print(f"Frame size: {frame_size} bytes")
    
    # Process in chunks
    chunk_size = 1024  # 512 samples at 16kHz 16-bit
    for i in range(0, len(pcm_bytes), chunk_size):
        chunk = pcm_bytes[i:i+chunk_size]
        if len(chunk) < chunk_size:
            chunk = chunk.ljust(chunk_size, b'\x00')
        
        result = vad.process_bytes(chunk, frame_size)
        if result[1]:  # speech_ended
            print(f"Chunk {i//chunk_size}: SPEECH ENDED! frame_audio={len(result[0]) if result[0] else 0} bytes, onset={result[2]}, end={result[3]}")
        elif i % (chunk_size * 50) == 0:
            # Periodic status
            audio = torch.frombuffer(bytearray(chunk), dtype=torch.int16).float() / 32768.0
            with torch.no_grad():
                prob = model(audio.unsqueeze(0), settings.audio_sample_rate).item()
            print(f"Chunk {i//chunk_size}: prob={prob:.4f}, triggered={vad.triggered}")
    
    # Flush
    flushed = vad.flush()
    if flushed:
        print(f"Flushed {len(flushed)} bytes")

if __name__ == "__main__":
    test_vad_with_file()