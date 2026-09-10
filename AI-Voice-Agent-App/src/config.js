const rawBase =
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_API_BASE ||
  'http://localhost:8001';

export const API_BASE = rawBase.replace(/\/$/, '');
export const WS_URL =
  import.meta.env.VITE_WS_URL ||
  `${API_BASE.replace(/^http/, 'ws')}/ws/voice`;

export function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('ngrok-skip-browser-warning', '1');
  return fetch(url, { ...options, headers });
}
