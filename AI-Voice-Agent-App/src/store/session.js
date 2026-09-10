import { create } from 'zustand'

export const useSessionStore = create((set) => ({
  sessionId: null,
  connectionStatus: 'disconnected',
  status: 'idle',
  setSessionId: (sessionId) => set({ sessionId }),
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  setStatus: (status) => set({ status }),
  reset: () => set({ sessionId: null, connectionStatus: 'disconnected', status: 'idle' }),
}))
