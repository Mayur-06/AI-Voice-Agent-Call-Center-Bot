import { create } from 'zustand';
import { useSessionStore } from './session';

const WS_URL = 'ws://localhost:8000/ws/voice';
const AUDIO_CHUNK_INTERVAL_MS = 250;

const callStore = create((set, get) => ({
  sessionId: null,
  status: 'idle',
  connectionStatus: 'disconnected',
  transcript: [],
  selectedPersona: null,
  selectedVoiceId: null,
  muted: false,
  error: null,
  latencies: { stt: null, llm: null, ttsFirstAudio: null, total: null },
  ws: null,
  mediaStream: null,
  mediaRecorder: null,
  audioContext: null,
  chunkTimer: null,
  audioChunks: [],
  ttsSourceNode: null,

  setSessionId: (sessionId) => {
    set({ sessionId });
    useSessionStore.getState().setSessionId(sessionId);
  },
  setStatus: (status) => set({ status }),
  setConnectionStatus: (connectionStatus) => {
    set({ connectionStatus });
    useSessionStore.getState().setConnectionStatus(connectionStatus);
  },
  setTranscript: (transcript) => set({ transcript }),
  setSelectedPersona: (selectedPersona) => set({ selectedPersona }),
  setSelectedVoiceId: (selectedVoiceId) => set({ selectedVoiceId }),
  setMuted: (muted) => set({ muted }),
  setError: (error) => set({ error }),
  setLatencies: (latencies) => set((prev) => ({ latencies: { ...prev.latencies, ...latencies } })),
  setWs: (ws) => set({ ws }),
  setMediaStream: (mediaStream) => set({ mediaStream }),
  setMediaRecorder: (mediaRecorder) => set({ mediaRecorder }),
  setAudioContext: (audioContext) => set({ audioContext }),
  setChunkTimer: (chunkTimer) => set({ chunkTimer }),
  setAudioChunks: (audioChunks) => set({ audioChunks }),
  setTtsSourceNode: (ttsSourceNode) => set({ ttsSourceNode }),

  addTranscriptEntry: (entry) =>
    set((prev) => ({
      transcript: [...prev.transcript, { id: crypto.randomUUID(), timestamp: new Date().toISOString(), ...entry }],
    })),

  reset: () => {
    set({
      sessionId: null,
      status: 'idle',
      connectionStatus: 'disconnected',
      transcript: [],
      selectedPersona: null,
      selectedVoiceId: null,
      muted: false,
      error: null,
      latencies: { stt: null, llm: null, ttsFirstAudio: null, total: null },
      ws: null,
      mediaStream: null,
      mediaRecorder: null,
      audioContext: null,
      chunkTimer: null,
      audioChunks: [],
      ttsSourceNode: null,
    });
    useSessionStore.getState().reset();
  },
}));

export { AUDIO_CHUNK_INTERVAL_MS, WS_URL };
export default callStore;
