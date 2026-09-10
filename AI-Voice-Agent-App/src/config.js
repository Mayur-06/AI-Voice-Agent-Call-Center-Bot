const HTTPS_API_FALLBACK = 'https://sphere-pry-concave.ngrok-free.dev';

function resolveApiBase() {
  const candidates = [import.meta.env.VITE_API_URL, import.meta.env.VITE_API_BASE]
    .filter(Boolean)
    .map((value) => value.replace(/\/$/, ''));

  const onHttps =
    typeof window !== 'undefined' && window.location.protocol === 'https:';

  if (onHttps) {
    const httpsUrl = candidates.find((value) => value.startsWith('https://'));
    return httpsUrl || HTTPS_API_FALLBACK;
  }

  return candidates[0] || 'http://localhost:8001';
}

export const API_BASE = resolveApiBase();
export const WS_URL =
  import.meta.env.VITE_WS_URL ||
  `${API_BASE.replace(/^http/, 'ws')}/ws/voice`;

export function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('ngrok-skip-browser-warning', '1');
  return fetch(url, { ...options, headers });
}
