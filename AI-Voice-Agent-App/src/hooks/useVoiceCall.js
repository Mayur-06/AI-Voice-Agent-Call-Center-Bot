import { useEffect, useRef, useCallback } from 'react';
import { WS_URL, AUDIO_CHUNK_INTERVAL_MS, API_BASE } from '@/store/callStore';
import { apiFetch } from '@/config';
import useCallStore from '@/store/callStore';
import { createGaplessPlayer } from '@/audio/gaplessPlayer';

const TARGET_SAMPLE_RATE = 16000;
// Speech loud enough to treat as the user interrupting the agent.
const BARGE_IN_PEAK_THRESHOLD = 0.06;
// Consecutive loud 20 ms frames required before we call it speech, so a cough
// or a key press does not cut the agent off.
const BARGE_IN_FRAMES = 5;
// Served as a real file rather than bundled: Vite inlines small assets as
// data: URLs, and addModule() rejects those under a strict CSP and in some
// browsers.
const PCM_WORKLET_URL = `${import.meta.env.BASE_URL || '/'}pcm-worklet.js`;

export function useVoiceCall() {
  const status = useCallStore((s) => s.status);
  const connectionStatus = useCallStore((s) => s.connectionStatus);
  const transcript = useCallStore((s) => s.transcript);
  const sessionId = useCallStore((s) => s.sessionId);
  const selectedPersona = useCallStore((s) => s.selectedPersona);
  const selectedVoiceId = useCallStore((s) => s.selectedVoiceId);
  const muted = useCallStore((s) => s.muted);
  const error = useCallStore((s) => s.error);
  const ragActive = useCallStore((s) => s.ragActive);
  const latencies = useCallStore((s) => s.latencies);
  const mediaStream = useCallStore((s) => s.mediaStream);
  const filler = useCallStore((s) => s.filler);

  const setStatus = useCallStore((s) => s.setStatus);
  const setConnectionStatus = useCallStore((s) => s.setConnectionStatus);
  const setSessionId = useCallStore((s) => s.setSessionId);
  const setTranscript = useCallStore((s) => s.setTranscript);
  const setError = useCallStore((s) => s.setError);
  const setSelectedPersona = useCallStore((s) => s.setSelectedPersona);
  const setSelectedVoiceId = useCallStore((s) => s.setSelectedVoiceId);
  const setMuted = useCallStore((s) => s.setMuted);
  const setMediaStream = useCallStore((s) => s.setMediaStream);
  const setAudioContext = useCallStore((s) => s.setAudioContext);
  const setRagActive = useCallStore((s) => s.setRagActive);
  const setFiller = useCallStore((s) => s.setFiller);
  const setLatencies = useCallStore((s) => s.setLatencies);
  const addTranscriptEntry = useCallStore((s) => s.addTranscriptEntry);
  const updateLastTranscriptEntry = useCallStore((s) => s.updateLastTranscriptEntry);

  const wsRef = useRef(null);
  const workletNodeRef = useRef(null);
  const captureCtxRef = useRef(null);
  const chunkIntervalRef = useRef(null);
  const pendingFramesRef = useRef([]);
  const ttsCtxRef = useRef(null);
  const playerRef = useRef(null);
  const bargeInFramesRef = useRef(0);
  const messageHandlerRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const stopCallRef = useRef(null);
  const connectingRef = useRef(false);
  const capturingRef = useRef(false);
  const mutedRef = useRef(muted);
  const analyserRef = useRef(null);
  const connectWebSocketRef = useRef(null);
  const playbackIdleTimerRef = useRef(null);
  const lastPlaybackSentRef = useRef(null);
  // Serialises decodeAudioData so chunks are scheduled in the order they
  // arrived, not the order the decoder happened to finish them.
  const decodeChainRef = useRef(Promise.resolve());
  const playbackGenerationRef = useRef(0);

  useEffect(() => {
    mutedRef.current = muted;
    if (workletNodeRef.current) {
      workletNodeRef.current.port.postMessage({ muted });
    }
  }, [muted]);

  // Debounced so a brief dip between arriving chunks is not reported as the
  // end of playback.
  const reportPlaybackState = useCallback((isPlaying) => {
    const send = (playing) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      if (lastPlaybackSentRef.current === playing) return;
      lastPlaybackSentRef.current = playing;
      try {
        ws.send(JSON.stringify({ type: 'playback_state', playing }));
      } catch {
        // Socket going away; the server's time-based backstop covers this.
      }
    };

    if (playbackIdleTimerRef.current) {
      clearTimeout(playbackIdleTimerRef.current);
      playbackIdleTimerRef.current = null;
    }
    if (isPlaying) {
      send(true);
      return;
    }
    playbackIdleTimerRef.current = setTimeout(() => {
      playbackIdleTimerRef.current = null;
      if (!(playerRef.current && playerRef.current.isPlaying)) send(false);
    }, 250);
  }, []);

  const ensurePlaybackContext = useCallback(() => {
    let ctx = ttsCtxRef.current;
    if (!ctx || ctx.state === 'closed') {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return null;
      ctx = new AudioContextClass();
      ttsCtxRef.current = ctx;
      setAudioContext(ctx);
      playerRef.current = null;
    }
    // A context created outside a user gesture starts suspended, and audio
    // would silently never play.
    if (ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
    }
    if (!playerRef.current) {
      playerRef.current = createGaplessPlayer(ctx, {
        onStateChange: (isPlaying) => {
          // UI state follows actual playback rather than server events, which
          // used to flip to idle while audio was still draining.
          setStatus(isPlaying ? 'speaking' : 'idle');
          // Tell the server too. It streams a 13s reply in about 2s, so
          // without this it unmutes the microphone while the agent is still
          // audible - the mic then hears the agent and answers it.
          reportPlaybackState(isPlaying);
        },
      });
    }
    return ctx;
  }, [setAudioContext, setStatus, reportPlaybackState]);

  const stopTtsPlayback = useCallback(() => {
    // Bump the generation so buffers still being decoded are discarded rather
    // than scheduled on top of whatever plays next.
    playbackGenerationRef.current += 1;
    if (playerRef.current) playerRef.current.stop();
  }, []);

  const handleServerStatus = useCallback((msg) => {
    const message = msg.message;
    switch (message) {
      case 'connected':
        setConnectionStatus('connected');
        setStatus('idle');
        setRagActive(false);
        setFiller(null);
        break;
      case 'authenticated':
        setConnectionStatus('authenticated');
        setStatus('idle');
        setRagActive(false);
        setFiller(null);
        break;
      case 'idle':
        setStatus('idle');
        setRagActive(false);
        setFiller(null);
        break;
      case 'retrieving_context':
        setRagActive(true);
        setStatus('processing');
        setFiller(null);
        break;
      case 'processing':
      case 'thinking':
      case 'transcribing':
      case 'transcribed':
        setRagActive(false);
        setStatus('processing');
        setFiller(null);
        break;
      case 'speaking':
        setRagActive(false);
        setStatus('speaking');
        setFiller(null);
        break;
      case 'interrupted':
        stopTtsPlayback();
        setRagActive(false);
        setStatus('idle');
        setFiller(null);
        break;
      case 'response_ready':
      case 'playback_stopped':
        stopTtsPlayback();
        setRagActive(false);
        setStatus('idle');
        setFiller(null);
        break;
      default:
        if (typeof message === 'string' && (message.startsWith('upload_received') || message.startsWith('decoded') || message.startsWith('vading')) && capturingRef.current) {
          const currentStatus = useCallStore.getState().status;
          if (currentStatus !== 'processing' && currentStatus !== 'speaking') {
            setStatus('listening');
          }
          setRagActive(false);
          setFiller(null);
        }
        break;
    }
  }, [setConnectionStatus, setStatus, setRagActive, stopTtsPlayback, setFiller]);

  const handleServerTranscript = useCallback((msg) => {
    const role = msg.role;
    const text = msg.text;
    if (role === 'user') {
      updateLastTranscriptEntry({ role: 'user', text, isPartial: false });
      setStatus('processing');
    } else if (role === 'assistant') {
      const currentTranscript = useCallStore.getState().transcript;
      const last = currentTranscript[currentTranscript.length - 1];
      if (!last || last.role !== 'assistant' || last.text !== text) {
        addTranscriptEntry({ role: 'assistant', text });
      }
    }
  }, [addTranscriptEntry, setStatus, updateLastTranscriptEntry]);

  const handleServerResponseAudio = useCallback((data) => {
    const ctx = ensurePlaybackContext();
    if (!ctx) return;

    // decodeAudioData is asynchronous and gives NO ordering guarantee: with
    // ~115 chunks in flight, roughly one in ten finished out of order, and the
    // player scheduled them in completion order rather than wire order. Chunk
    // 11 played before chunk 10, 14 before 13 - which is heard as the voice
    // breaking up and doubling back on itself. (The saved recording was always
    // fine because the server composes that from PCM in the correct order.)
    //
    // Chaining the decodes restores wire order. Decoding ~120ms of audio takes
    // well under a millisecond, so serialising costs no measurable latency.
    const generation = playbackGenerationRef.current;
    decodeChainRef.current = decodeChainRef.current
      .then(() => ctx.decodeAudioData(data.slice(0)))
      .then((buffer) => {
        // Dropped if barge-in reset playback while this was decoding.
        if (generation !== playbackGenerationRef.current) return;
        if (playerRef.current) playerRef.current.schedule(buffer);
      })
      .catch((err) => {
        console.error('[voice] decodeAudioData failed', err);
      });
  }, [ensurePlaybackContext]);

  const handleServerError = useCallback((msg) => {
    const errorMessage = msg.message;
    setError(errorMessage);
    setStatus('idle');
  }, [setError, setStatus]);

  const handleServerSentiment = useCallback((msg) => {
    const label = msg.label;
    if (label === 'frustrated') {
      setStatus('processing');
    }
  }, [setStatus]);

  const handleServerFiller = useCallback((msg) => {
    const text = msg.text;
    setFiller(text);
  }, [setFiller]);

  const handleServerMessage = useCallback((event) => {
    if (typeof event.data === 'string') {
      try {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
          case 'status':
            handleServerStatus(msg);
            break;
          case 'transcript_final':
            handleServerTranscript(msg);
            break;
          case 'turn_started':
            setStatus('processing');
            setRagActive(false);
            setFiller(null);
            break;
          case 'turn_ended':
            // Let queued audio finish; the player reports idle when it drains.
            setRagActive(false);
            setFiller(null);
            if (!(playerRef.current && playerRef.current.isPlaying)) {
              setStatus('idle');
            }
            break;
          case 'response_audio':
            // Metadata event for TTS first audio latency - actual audio comes as binary messages
            if (msg.latency_ms !== undefined) {
              setLatencies({ ttsFirstAudio: msg.latency_ms });
            }
            break;
          case 'sentiment':
            handleServerSentiment(msg);
            break;
          case 'filler':
            handleServerFiller(msg);
            break;
          case 'error':
            handleServerError(msg);
            break;
          case 'pong':
            break;
          case 'latencies':
            setLatencies({
              stt: msg.stt ?? null,
              llm: msg.llm ?? null,
              ...(msg.ttsFirstAudio != null ? { ttsFirstAudio: msg.ttsFirstAudio } : {}),
              total: msg.total ?? null,
            });
            break;
          default:
            break;
        }
      } catch {
        // Ignore unparseable messages
      }
    } else if (event.data instanceof Blob) {
      event.data.arrayBuffer().then((ab) => {
        handleServerResponseAudio(ab);
      });
    } else if (event.data instanceof ArrayBuffer) {
      handleServerResponseAudio(event.data);
    }
  }, [
    handleServerStatus,
    handleServerTranscript,
    handleServerResponseAudio,
    handleServerError,
    handleServerSentiment,
    handleServerFiller,
    setStatus,
    setRagActive,
    setFiller,
    setLatencies,
  ]);

  const connectWebSocket = useCallback((sessionId) => {
    return new Promise((resolve, reject) => {
      try {
        const oldWs = wsRef.current;
        if (oldWs && (oldWs.readyState === WebSocket.OPEN || oldWs.readyState === WebSocket.CONNECTING)) {
          try {
            oldWs.close();
          } catch {
            // Already closing.
          }
        }

        const ws = new WebSocket(`${WS_URL}/${sessionId}`);
        ws.binaryType = 'arraybuffer';
        wsRef.current = ws;

        ws.onopen = () => {
          setConnectionStatus('connected');
          reconnectAttemptsRef.current = 0;

          ws.send(JSON.stringify({ type: 'start_call', session_id: sessionId }));
          ws.send(JSON.stringify({ type: 'ping', session_id: sessionId }));
          resolve();
        };

        ws.onmessage = (event) => {
          if (messageHandlerRef.current) messageHandlerRef.current(event);
        };

        ws.onerror = () => {
          // Let onclose handle terminal state to avoid duplicate transitions.
        };

        ws.onclose = (event) => {
          setConnectionStatus('disconnected');
          stopTtsPlayback();
          setStatus('idle');

          if (!event.wasClean && reconnectAttemptsRef.current < 3) {
            const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 8000);
            reconnectAttemptsRef.current += 1;
            setTimeout(() => {
              if (sessionId) {
                connectWebSocketRef.current(sessionId);
              }
            }, delay);
          }
        };
      } catch (error) {
        reject(error);
      }
    });
    // handleServerMessage is intentionally not a dependency: it is read
    // through messageHandlerRef so the open socket always calls the latest
    // version without needing to reconnect.
  }, [setConnectionStatus, stopTtsPlayback, setStatus]);

  const startMicCapture = useCallback(async () => {
    if (capturingRef.current) return false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      setMediaStream(stream);
      setStatus('listening');
      capturingRef.current = true;

      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      // Capture at the target rate directly: the browser resamples natively,
      // with proper anti-aliasing. Hand-rolled nearest-neighbour decimation
      // from 48 kHz folded everything above 8 kHz back into the audible band
      // and measurably degraded transcription.
      const captureCtx = new AudioContextClass({ sampleRate: TARGET_SAMPLE_RATE });
      if (captureCtx.state === 'suspended') {
        await captureCtx.resume();
      }
      captureCtxRef.current = captureCtx;

      await captureCtx.audioWorklet.addModule(PCM_WORKLET_URL);

      const source = captureCtx.createMediaStreamSource(stream);
      const analyser = captureCtx.createAnalyser();
      analyser.fftSize = 2048;
      analyserRef.current = analyser;

      const worklet = new AudioWorkletNode(captureCtx, 'pcm-capture');
      workletNodeRef.current = worklet;
      worklet.port.postMessage({ muted: mutedRef.current });

      pendingFramesRef.current = [];
      bargeInFramesRef.current = 0;

      worklet.port.onmessage = (event) => {
        const { frame, peak } = event.data;
        if (!frame) return;
        pendingFramesRef.current.push(new Int16Array(frame));

        // Client-side barge-in. The user should be able to cut the agent off
        // without waiting for the server to notice.
        if (playerRef.current && playerRef.current.isPlaying) {
          if (peak >= BARGE_IN_PEAK_THRESHOLD) {
            bargeInFramesRef.current += 1;
            if (bargeInFramesRef.current >= BARGE_IN_FRAMES) {
              bargeInFramesRef.current = 0;
              playerRef.current.stop();
              const ws = wsRef.current;
              if (ws && ws.readyState === WebSocket.OPEN) {
                try {
                  ws.send(JSON.stringify({ type: 'stop_playback' }));
                } catch {
                  // Socket is going away; the server will clean up.
                }
              }
            }
          } else {
            bargeInFramesRef.current = 0;
          }
        } else {
          bargeInFramesRef.current = 0;
        }
      };

      // The worklet is a sink here; connecting it to the destination would
      // route the microphone to the speakers.
      source.connect(analyser);
      analyser.connect(worklet);

      chunkIntervalRef.current = window.setInterval(() => {
        const frames = pendingFramesRef.current;
        if (frames.length === 0 || mutedRef.current || !capturingRef.current) return;

        const currentWs = wsRef.current;
        if (!currentWs || currentWs.readyState !== WebSocket.OPEN) return;

        // Send every captured sample. The previous implementation re-framed
        // into fixed 512-sample blocks and discarded the remainder on each
        // tick without carrying it over, silently dropping roughly an eighth
        // of everything the user said.
        let total = 0;
        for (const f of frames) total += f.length;
        const combined = new Int16Array(total);
        let offset = 0;
        for (const f of frames) {
          combined.set(f, offset);
          offset += f.length;
        }
        frames.length = 0;

        try {
          currentWs.send(combined.buffer);
        } catch (err) {
          console.error('[voice] ws send failed', err);
        }
      }, AUDIO_CHUNK_INTERVAL_MS);

      return true;
    } catch (error) {
      capturingRef.current = false;
      setError(error instanceof Error ? error.message : 'Microphone access failed');
      return false;
    }
  }, [setMediaStream, setStatus, setError]);

  const startCall = useCallback(async (existingSessionId) => {
    if (connectingRef.current) return;
    connectingRef.current = true;

    let newSessionId = existingSessionId;

    if (!newSessionId) {
      if (!selectedPersona) {
        connectingRef.current = false;
        setError('No persona selected');
        setStatus('idle');
        setConnectionStatus('disconnected');
        return;
      }

      try {
        const response = await apiFetch(`${API_BASE}/api/sessions`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            persona_id: selectedPersona,
            selected_voice: selectedVoiceId || null,
          }),
        });

        if (!response.ok) {
          throw new Error('Failed to create session');
        }

        const data = await response.json();
        newSessionId = data.id;
      } catch (error) {
        setError(error instanceof Error ? error.message : 'Failed to create session');
        setStatus('idle');
        setConnectionStatus('disconnected');
        connectingRef.current = false;
        return;
      }
    }

    setSessionId(newSessionId);
    setStatus('idle');
    setConnectionStatus('connecting');
    if (!existingSessionId) {
        setTranscript([]);
    }
    setError(null);
    setFiller(null);
    setLatencies({ stt: null, llm: null, ttsFirstAudio: null, total: null });

    try {
      await connectWebSocketRef.current(newSessionId);
      if (!capturingRef.current) {
        try {
          await startMicCapture();
        } catch {
          // Mic access failed; error is surfaced via setError inside startMicCapture.
        }
      }
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to start call');
      setStatus('idle');
      setConnectionStatus('disconnected');
    } finally {
      connectingRef.current = false;
    }
  }, [selectedPersona, selectedVoiceId, setSessionId, setStatus, setConnectionStatus, setTranscript, setError, setFiller, setLatencies, startMicCapture]);

  const stopCall = useCallback(() => {
    connectingRef.current = false;
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: 'stop_call', session_id: sessionId }));
      } catch {
        // ignore send errors on close
      }
      ws.close(1000, 'Client ended call');
    }

    stopTtsPlayback();

    if (chunkIntervalRef.current) {
      clearInterval(chunkIntervalRef.current);
      chunkIntervalRef.current = null;
    }

    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.port.onmessage = null;
        workletNodeRef.current.disconnect();
      } catch {
        // Already torn down.
      }
      workletNodeRef.current = null;
    }
    pendingFramesRef.current = [];

    if (analyserRef.current) {
      try {
        analyserRef.current.disconnect();
      } catch {
        // Already disconnected.
      }
      analyserRef.current = null;
    }

    if (mediaStream) {
      mediaStream.getTracks().forEach((track) => track.stop());
    }

    if (captureCtxRef.current && captureCtxRef.current.state !== 'closed') {
      captureCtxRef.current.close().catch(function() {});
    }
    captureCtxRef.current = null;
    if (ttsCtxRef.current && ttsCtxRef.current.state !== 'closed') {
      ttsCtxRef.current.close().catch(function() {});
    }
    ttsCtxRef.current = null;
    playerRef.current = null;

    capturingRef.current = false;

    setStatus('idle');
    setConnectionStatus('disconnected');
    setMediaStream(null);
    setAudioContext(null);
  }, [sessionId, mediaStream, stopTtsPlayback, setStatus, setConnectionStatus, setMediaStream, setAudioContext]);

  const stopCapture = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: 'stop_listening', session_id: sessionId }));
      } catch (e) {
        console.error('[voice] Failed to send stop_listening:', e);
      }
    }

    capturingRef.current = false;
    setStatus('processing');
    stopTtsPlayback();

    if (chunkIntervalRef.current) {
      clearInterval(chunkIntervalRef.current);
      chunkIntervalRef.current = null;
    }

    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.port.onmessage = null;
        workletNodeRef.current.disconnect();
      } catch {
        // Already torn down.
      }
      workletNodeRef.current = null;
    }
    pendingFramesRef.current = [];

    if (analyserRef.current) {
      try {
        analyserRef.current.disconnect();
      } catch {
        // Already disconnected.
      }
      analyserRef.current = null;
    }

    if (captureCtxRef.current && captureCtxRef.current.state !== 'closed') {
      captureCtxRef.current.close().catch(function() {});
    }
    captureCtxRef.current = null;

    if (mediaStream) {
      mediaStream.getTracks().forEach((track) => track.stop());
      setMediaStream(null);
    }
  }, [sessionId, mediaStream, setMediaStream, stopTtsPlayback, setStatus]);

  const toggleCapture = useCallback(async () => {
    if (capturingRef.current) {
      stopCapture();
      return;
    }
    const ok = await startMicCapture();
    if (!ok) {
      setError('Microphone access failed');
    }
  }, [stopCapture, startMicCapture, setError]);

  const sendTextFallback = useCallback((text) => {
    const trimmed = (text || '').trim();
    if (!trimmed) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setError('WebSocket is not connected');
      return;
    }
    ws.send(JSON.stringify({ type: 'external_transcript', data: { text: trimmed }, session_id: sessionId }));
  }, [sessionId, setError]);

  const toggleMute = useCallback(() => {
    setMuted(!muted);
  }, [muted, setMuted]);

  const selectVoice = useCallback((voiceId) => {
    setSelectedVoiceId(voiceId);
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'voice_select', voice_id: voiceId }));
    }
  }, [setSelectedVoiceId]);

  useEffect(() => {
    messageHandlerRef.current = handleServerMessage;
  }, [handleServerMessage]);

  useEffect(() => {
    connectWebSocketRef.current = connectWebSocket;
  }, [connectWebSocket]);

  useEffect(() => {
    stopCallRef.current = stopCall;
  }, [stopCall]);

  useEffect(() => {
    return () => {
      if (stopCallRef.current) {
        stopCallRef.current();
      }
    };
  }, []);

  return {
    status,
    connectionStatus,
    transcript,
    sessionId,
    selectedPersona,
    selectedVoiceId,
    muted,
    error,
    ragActive,
    latencies,
    filler,
    isCapturing: !!mediaStream,
    startCall,
    stopCall,
    stopCapture,
    toggleCapture,
    sendTextFallback,
    toggleMute,
    setSelectedPersona,
    setSelectedVoiceId,
    selectVoice,
    setStatus,
    setError,
  };
}