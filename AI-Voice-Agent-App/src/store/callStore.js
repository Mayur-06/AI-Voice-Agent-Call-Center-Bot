import { create } from 'zustand';
import { useSessionStore } from './session';
import { WS_URL, API_BASE } from '@/config';

const AUDIO_CHUNK_INTERVAL_MS = 250;

const callStore = create((set) => ({
  sessionId: null,
  status: 'idle',
  connectionStatus: 'disconnected',
  transcript: [],
  selectedPersona: null,
  selectedVoiceId: null,
  muted: false,
  error: null,
  latencies: { stt: null, llm: null, ttsFirstAudio: null, total: null },
  uploadedDocuments: [],
  ragActive: false,
  ws: null,
  mediaStream: null,
  mediaRecorder: null,
  audioContext: null,
  chunkTimer: null,
  audioChunks: [],
  ttsSourceNode: null,
  filler: null,
  localRecordings: [],

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
  setUploadedDocuments: (uploadedDocuments) =>
    set((prev) => ({
      uploadedDocuments:
        typeof uploadedDocuments === 'function'
          ? uploadedDocuments(prev.uploadedDocuments)
          : uploadedDocuments,
    })),
  setRagActive: (ragActive) => set({ ragActive }),
  setWs: (ws) => set({ ws }),
  setMediaStream: (mediaStream) => set({ mediaStream }),
  setMediaRecorder: (mediaRecorder) => set({ mediaRecorder }),
  setAudioContext: (audioContext) => set({ audioContext }),
  setChunkTimer: (chunkTimer) => set({ chunkTimer }),
  setAudioChunks: (audioChunks) => set({ audioChunks }),
  setTtsSourceNode: (ttsSourceNode) => set({ ttsSourceNode }),
  setFiller: (filler) => set({ filler }),
  addLocalRecording: (recording) =>
    set((prev) => ({
      localRecordings: [...prev.localRecordings, recording],
    })),
  clearLocalRecordings: () => set({ localRecordings: [] }),

  addTranscriptEntry: (entry) =>
    set((prev) => {
      const last = prev.transcript[prev.transcript.length - 1];
      if (last && last.role === entry.role && last.text === entry.text) {
        return prev;
      }
      return {
        transcript: [...prev.transcript, { id: crypto.randomUUID(), timestamp: new Date().toISOString(), ...entry }],
      };
    }),

  updateLastTranscriptEntry: (updates) =>
    set((prev) => {
      const transcript = [...prev.transcript];
      if (transcript.length === 0) {
        return { transcript: [{ id: crypto.randomUUID(), timestamp: new Date().toISOString(), ...updates }] };
      }
      const last = transcript[transcript.length - 1];
      if (last.role === 'user') {
        transcript[transcript.length - 1] = { ...last, ...updates };
      } else {
        transcript.push({ id: crypto.randomUUID(), timestamp: new Date().toISOString(), ...updates });
      }
      return { transcript };
    }),

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
      uploadedDocuments: [],
      ragActive: false,
      ws: null,
      mediaStream: null,
      mediaRecorder: null,
      audioContext: null,
      chunkTimer: null,
      audioChunks: [],
      ttsSourceNode: null,
      filler: null,
      localRecordings: [],
    });
    useSessionStore.getState().reset();
  },
}));

export { AUDIO_CHUNK_INTERVAL_MS, WS_URL, API_BASE };
export default callStore;
