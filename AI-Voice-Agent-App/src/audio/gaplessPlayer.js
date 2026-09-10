// Gapless playback for streamed TTS chunks.
//
// The previous implementation started each buffer from the previous one's
// `onended` callback. That callback fires on the main thread, so every chunk
// boundary added a scheduling gap and speech came out stilted. Now that the
// backend streams many small chunks per sentence rather than one WAV, that
// approach would be audibly broken.
//
// Instead each chunk is scheduled against a running timeline on the audio
// clock, so consecutive buffers are sample-accurate.

// How far ahead of `currentTime` the first chunk is scheduled. Absorbs jitter
// without being perceptible.
const SCHEDULE_LEAD_S = 0.04;

export function createGaplessPlayer(ctx, { onStateChange } = {}) {
  let nextStartTime = 0;
  let pending = 0;
  const active = new Set();

  function notify() {
    if (onStateChange) onStateChange(pending > 0);
  }

  return {
    get isPlaying() {
      return pending > 0;
    },

    schedule(audioBuffer) {
      const now = ctx.currentTime;
      // If the queue has drained, restart the timeline from now.
      const startAt = Math.max(now + SCHEDULE_LEAD_S, nextStartTime);

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);

      pending += 1;
      active.add(source);
      source.onended = () => {
        active.delete(source);
        pending -= 1;
        if (pending <= 0) {
          pending = 0;
          nextStartTime = 0;
        }
        notify();
      };

      source.start(startAt);
      nextStartTime = startAt + audioBuffer.duration;
      notify();
      return startAt;
    },

    // Barge-in: drop everything already scheduled.
    stop() {
      for (const source of active) {
        source.onended = null;
        try {
          source.stop();
        } catch {
          // Already ended; nothing to do.
        }
      }
      active.clear();
      pending = 0;
      nextStartTime = 0;
      notify();
    },
  };
}
