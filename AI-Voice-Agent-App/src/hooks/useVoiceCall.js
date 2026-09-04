import { useEffect, useRef, useCallback } from 'react';
import { WS_URL, AUDIO_CHUNK_INTERVAL_MS, API_BASE } from '@/store/callStore';
import useCallStore from '@/store/callStore';

const TARGET_SAMPLE_RATE = 16000;

function downMixAndResample(inputBuffer, outputSampleRate) {
  const inputSampleRate = inputBuffer.sampleRate;
  const inputData = inputBuffer.getChannelData(0);
  const ratio = inputSampleRate / outputSampleRate;
  const outputLength = Math.floor(inputData.length / ratio);
  const output = new Int16Array(outputLength);

  for (let i = 0; i < outputLength; i++) {
    const srcIndex = Math.floor(i * ratio);
    const sample = Math.max(-1, Math.min(1, inputData[srcIndex] != null ? inputData[srcIndex] : 0));
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }

  return output;
}

function encodePcmChunk(int16Array) {
  const buffer = new Uint8Array(int16Array.byteLength);
  const view = new DataView(buffer.buffer);
  for (let i = 0; i < int16Array.length; i++) {
    view.setInt16(i * 2, int16Array[i], true);
  }
  return buffer;
}

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
  const audioContext = useCallStore((s) => s.audioContext);
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
  const processorRef = useRef(null);
  const chunkIntervalRef = useRef(null);
  const ttsQueueRef = useRef([]);
  const isPlayingTtsRef = useRef(false);
  const ttsCtxRef = useRef(null);
  const currentTtsSourceRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const stopCallRef = useRef(null);
  const connectingRef = useRef(false);
  const capturingRef = useRef(false);
  const mutedRef = useRef(muted);
  const analyserRef = useRef(null);
  const connectWebSocketRef = useRef(null);
  const playNextTtsChunkRef = useRef(null);

  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  function playNextTtsChunk() {
    const ctx = ttsCtxRef.current || audioContext;
    if (!ctx || ttsQueueRef.current.length === 0) {
      isPlayingTtsRef.current = false;
      currentTtsSourceRef.current = null;
      if (ttsQueueRef.current.length === 0) {
        setStatus('idle');
      }
      return;
    }

    isPlayingTtsRef.current = true;
    setStatus('speaking');

    const buffer = ttsQueueRef.current.shift();
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    currentTtsSourceRef.current = source;
    source.onended = () => {
      if (currentTtsSourceRef.current === source) {
        currentTtsSourceRef.current = null;
      }
      playNextTtsChunk();
    };
    source.start();
  }

  useEffect(() => {
    playNextTtsChunkRef.current = playNextTtsChunk;
  });

  const stopTtsPlayback = useCallback(() => {
    if (currentTtsSourceRef.current) {
      try {
        currentTtsSourceRef.current.onended = null;
        currentTtsSourceRef.current.stop();
      } catch {
        // ignore stop errors on already-ended sources
      }
      currentTtsSourceRef.current = null;
    }
    ttsQueueRef.current = [];
    isPlayingTtsRef.current = false;
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
        if ((message.startsWith('upload_received') || message.startsWith('decoded') || message.startsWith('vading')) && capturingRef.current) {
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
      setStatus('idle');
    }
  }, [addTranscriptEntry, setStatus, updateLastTranscriptEntry]);

  const handleServerPartialTranscript = useCallback((msg) => {
    updateLastTranscriptEntry({ role: 'user', text: msg.text, isPartial: true });
  }, [updateLastTranscriptEntry]);

  const handleServerResponseAudio = useCallback((data) => {
    const ctx = audioContext || ttsCtxRef.current;
    if (!ctx) {
      try {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        const newCtx = new AudioContextClass();
        setAudioContext(newCtx);
        ttsCtxRef.current = newCtx;
      } catch {
        return;
      }
    }

    const targetCtx = audioContext || ttsCtxRef.current;
    targetCtx.decodeAudioData(data.slice(0), (buffer) => {
      ttsQueueRef.current.push(buffer);
      if (!isPlayingTtsRef.current) {
        playNextTtsChunkRef.current();
      }
    }, () => {
      const blob = new Blob([data], { type: 'audio/mpeg' });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => {
        URL.revokeObjectURL(url);
        if (isPlayingTtsRef.current) {
          isPlayingTtsRef.current = false;
          currentTtsSourceRef.current = null;
          setStatus('idle');
        }
        playNextTtsChunkRef.current();
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        if (isPlayingTtsRef.current) {
          isPlayingTtsRef.current = false;
          currentTtsSourceRef.current = null;
          setStatus('idle');
        }
        playNextTtsChunkRef.current();
      };
      isPlayingTtsRef.current = true;
      setStatus('speaking');
      audio.play().catch(() => {
        URL.revokeObjectURL(url);
        isPlayingTtsRef.current = false;
        setStatus('idle');
        playNextTtsChunkRef.current();
      });
    });
  }, [audioContext, setStatus, setAudioContext]);

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

  const handleServerSentenceEnd = useCallback((msg) => {
    const text = msg.text;
    addTranscriptEntry({ role: 'assistant', text, isPartial: false });
  }, [addTranscriptEntry]);

  const handleServerFiller = useCallback((msg) => {
    const text = msg.text;
    setFiller(text);
    addTranscriptEntry({ role: 'assistant', text, isFiller: true });
  }, [setFiller, addTranscriptEntry]);

  const handleServerMessage = useCallback((event) => {
    if (typeof event.data === 'string') {
      try {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
          case 'status':
            handleServerStatus(msg);
            break;
          case 'transcript':
            handleServerTranscript(msg);
            break;
          case 'response_ready':
            if (!msg.role || msg.role === 'assistant') {
              const currentTranscript = useCallStore.getState().transcript;
              const last = currentTranscript[currentTranscript.length - 1];
              const text = msg.text;
              if (!last || last.role !== 'assistant' || last.text !== text) {
                addTranscriptEntry({ role: 'assistant', text });
              }
            }
            setStatus('idle');
            break;
          case 'partial_transcript':
            handleServerPartialTranscript(msg);
            break;
          case 'response_text':
            addTranscriptEntry({ role: 'assistant', text: msg.text });
            setStatus('idle');
            break;
          case 'response_audio':
            if (!(event.data instanceof Blob) && event.data instanceof ArrayBuffer) {
              handleServerResponseAudio(event.data);
            }
            break;
          case 'sentiment':
            handleServerSentiment(msg);
            break;
          case 'sentence_end':
            handleServerSentenceEnd(msg);
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
              ttsFirstAudio: msg.ttsFirstAudio ?? null,
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
    handleServerPartialTranscript,
    handleServerResponseAudio,
    handleServerError,
    handleServerSentiment,
    handleServerSentenceEnd,
    handleServerFiller,
    addTranscriptEntry,
    updateLastTranscriptEntry,
    setStatus,
    setLatencies,
  ]);

  const connectWebSocket = useCallback((sessionId) => {
    return new Promise((resolve, reject) => {
      try {
        const oldWs = wsRef.current;
        if (oldWs && (oldWs.readyState === WebSocket.OPEN || oldWs.readyState === WebSocket.CONNECTING)) {
          try { oldWs.close(); } catch {}
        }

        const ws = new WebSocket(`${WS_URL}/${sessionId}`);
        ws.binaryType = 'arraybuffer';
        wsRef.current = ws;

        ws.onopen = () => {
          setConnectionStatus('connected');
          reconnectAttemptsRef.current = 0;

          const authPayload = {
            type: 'auth',
            session_id: sessionId,
            persona_id: selectedPersona,
            voice_id: selectedVoiceId,
          };
          ws.send(JSON.stringify(authPayload));

          ws.send(JSON.stringify({ type: 'ping', session_id: sessionId }));
          resolve();
        };

        ws.onmessage = (event) => {
          handleServerMessage(event);
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
  }, [selectedPersona, selectedVoiceId, setConnectionStatus, stopTtsPlayback, setStatus, handleServerMessage]);

  const startMicCapture = useCallback(async () => {
    if (capturingRef.current) return false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: TARGET_SAMPLE_RATE,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      setMediaStream(stream);
      setStatus('listening');
      capturingRef.current = true;

      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      const audioContext = new AudioContextClass({ sampleRate: TARGET_SAMPLE_RATE });
      setAudioContext(audioContext);
      ttsCtxRef.current = audioContext;

      const source = audioContext.createMediaStreamSource(stream);
      processorRef.current = audioContext.createScriptProcessor(4096, 1, 1);

      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 2048;
      analyserRef.current = analyser;

      const chunks = [];

      processorRef.current.onaudioprocess = (event) => {
        if (mutedRef.current) return;
        const pcm = downMixAndResample(event.inputBuffer, TARGET_SAMPLE_RATE);
        chunks.push(pcm);
      };

      source.connect(analyser);
      analyser.connect(processorRef.current);
      processorRef.current.connect(audioContext.destination);

      chunkIntervalRef.current = window.setInterval(() => {
        if (chunks.length === 0 || mutedRef.current || !capturingRef.current) return;
        const totalLength = chunks.reduce((sum, c) => sum + c.length, 0);
        const combined = new Int16Array(totalLength);
        let offset = 0;
        for (const chunk of chunks) {
          combined.set(chunk, offset);
          offset += chunk.length;
        }
        chunks.length = 0;

        const currentWs = wsRef.current;
        if (currentWs && currentWs.readyState === WebSocket.OPEN) {
          currentWs.send(encodePcmChunk(combined));
        }
      }, AUDIO_CHUNK_INTERVAL_MS);

      return true;
    } catch (error) {
      capturingRef.current = false;
      setError(error instanceof Error ? error.message : 'Microphone access failed');
      return false;
    }
  }, [setMediaStream, setStatus, setAudioContext, setError]);

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
        const response = await fetch(`${API_BASE}/api/sessions`, {
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
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to start call');
      setStatus('idle');
      setConnectionStatus('disconnected');
    } finally {
      connectingRef.current = false;
    }
  }, [selectedPersona, selectedVoiceId, setSessionId, setStatus, setConnectionStatus, setTranscript, setError, setFiller, setLatencies]);

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

    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    if (analyserRef.current) {
      try { analyserRef.current.disconnect(); } catch {}
      analyserRef.current = null;
    }

    if (mediaStream) {
      mediaStream.getTracks().forEach((track) => track.stop());
    }

    if (audioContext && audioContext.state !== 'closed') {
      audioContext.close().catch(function() {});
    }
    if (ttsCtxRef.current && ttsCtxRef.current !== audioContext && ttsCtxRef.current.state !== 'closed') {
      ttsCtxRef.current.close().catch(function() {});
    }

    capturingRef.current = false;

    setStatus('idle');
    setConnectionStatus('disconnected');
    setMediaStream(null);
    setAudioContext(null);
  }, [sessionId, mediaStream, audioContext, stopTtsPlayback, setStatus, setConnectionStatus, setMediaStream, setAudioContext]);

  const stopCapture = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: 'stop_listening', session_id: sessionId }));
      } catch (e) {
        console.error('Failed to send stop_listening:', e);
      }
    }

    capturingRef.current = false;
    setStatus('processing');
    stopTtsPlayback();

    if (chunkIntervalRef.current) {
      clearInterval(chunkIntervalRef.current);
      chunkIntervalRef.current = null;
    }

    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    if (analyserRef.current) {
      try { analyserRef.current.disconnect(); } catch {}
      analyserRef.current = null;
    }

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
    ws.send(JSON.stringify({ type: 'transcript', text: trimmed, session_id: sessionId }));
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
    analyser: analyserRef.current,
  };
}
