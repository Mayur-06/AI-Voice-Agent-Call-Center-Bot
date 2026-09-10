// Resolves the backend base URL for the current page.
//
// A page served over HTTPS cannot call an http:// API or open a ws:// socket -
// browsers block both as mixed content - so an HTTPS origin must resolve to an
// HTTPS backend or the call silently never connects.
//
// Configure VITE_API_URL (and optionally VITE_WS_URL) at build time. There is
// deliberately no hardcoded fallback host: this previously pointed at a free
// ngrok subdomain, which is reassigned whenever the tunnel restarts, so any
// build that fell through to it broke without warning.
const DEV_API_BASE = 'http://localhost:8001';

function resolveApiBase() {
  const candidates = [import.meta.env.VITE_API_URL, import.meta.env.VITE_API_BASE]
    .filter(Boolean)
    .map((value) => value.replace(/\/$/, ''));

  const onHttps =
    typeof window !== 'undefined' && window.location.protocol === 'https:';

  if (onHttps) {
    const httpsUrl = candidates.find((value) => value.startsWith('https://'));
    if (httpsUrl) return httpsUrl;
    // Same-origin is the one safe guess: it works when the API is reverse
    // proxied under the site that served this page.
    const sameOrigin = window.location.origin;
    if (candidates.length) {
      console.error(
        `[config] VITE_API_URL is not https (${candidates[0]}); an HTTPS page cannot call it. ` +
          `Falling back to same-origin ${sameOrigin}.`,
      );
    } else {
      console.error(
        `[config] VITE_API_URL is not set. Falling back to same-origin ${sameOrigin}.`,
      );
    }
    return sameOrigin;
  }

  return candidates[0] || DEV_API_BASE;
}

export const API_BASE = resolveApiBase();
export const WS_URL =
  import.meta.env.VITE_WS_URL ||
  `${API_BASE.replace(/^http/, 'ws')}/ws/voice`;

export function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  // Harmless elsewhere; suppresses ngrok's HTML interstitial when the backend
  // happens to be exposed through an ngrok tunnel.
  headers.set('ngrok-skip-browser-warning', '1');
  return fetch(url, { ...options, headers });
}
