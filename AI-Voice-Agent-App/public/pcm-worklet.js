/* global AudioWorkletProcessor, registerProcessor */
// Microphone capture processor.
//
// Replaces a ScriptProcessorNode, which ran on the main thread and so competed
// with React rendering: every re-render added jitter to audio capture and
// callback overruns dropped samples outright.
//
// The capture AudioContext is created at 16 kHz, so the browser performs the
// resampling natively (with proper anti-aliasing filters). This processor only
// converts float samples to little-endian PCM16 and batches them, rather than
// decimating by hand.

const FRAME_SAMPLES = 320; // 20 ms at 16 kHz

class PCMCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Int16Array(FRAME_SAMPLES);
    this._offset = 0;
    this._muted = false;
    this.port.onmessage = (event) => {
      if (event.data && typeof event.data.muted === 'boolean') {
        this._muted = event.data.muted;
      }
    };
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel) return true;

    if (this._muted) {
      // Keep the node alive but emit nothing while muted.
      this._offset = 0;
      return true;
    }

    let peak = 0;
    for (let i = 0; i < channel.length; i += 1) {
      const sample = channel[i];
      const abs = sample < 0 ? -sample : sample;
      if (abs > peak) peak = abs;

      const clamped = sample > 1 ? 1 : sample < -1 ? -1 : sample;
      this._buffer[this._offset] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      this._offset += 1;

      if (this._offset === FRAME_SAMPLES) {
        // Transfer a copy so the buffer can be reused immediately.
        const frame = this._buffer.slice();
        this.port.postMessage({ frame, peak }, [frame.buffer]);
        this._offset = 0;
        peak = 0;
      }
    }
    return true;
  }
}

registerProcessor('pcm-capture', PCMCaptureProcessor);
