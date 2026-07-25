/**
 * Backend base-URL resolver.
 *
 * In dev (Vite), the backend is reachable at the same origin through the
 * Vite proxy, so the base is an empty string ("") and callers can use
 * relative URLs like "/api/v1/...". In production (running inside the
 * Tauri shell), the webview origin is `tauri://localhost` so relative
 * URLs do not work — callers must prefix every request with
 * `http://127.0.0.1:<port>` where `<port>` was chosen by the backend
 * sidecar and passed to the frontend via the `backend-ready` Tauri event.
 *
 * Protocol (see specs/052-tauri-desktop-packaging/contracts/sidecar-handshake.md):
 *   - Rust shell spawns the PyInstaller backend sidecar.
 *   - Backend prints `XLIGHT_BACKEND_PORT=<port>` on stdout.
 *   - Rust parses it, caches the port, and emits the `backend-ready`
 *     Tauri event with payload `{port}`.
 *   - Frontend listens and resolves a promise.
 *   - If the frontend attaches too late, it can invoke the Rust
 *     `get_backend_port` command which returns the cached port.
 */

let resolvedBase: string | null = null;
let resolution: Promise<string> | null = null;

const HANDSHAKE_TIMEOUT_MS = 30_000;

function isDev(): boolean {
  return typeof import.meta !== "undefined" && Boolean(import.meta.env?.DEV);
}

function isTauri(): boolean {
  return typeof window !== "undefined" && Boolean((window as any).__TAURI_INTERNALS__ || (window as any).__TAURI__);
}

/**
 * Not every call site was migrated to `apiFetch`/`apiEventSource` (see
 * apiClient.ts) -- several screens still call bare `fetch("/api/...")` /
 * `new EventSource("/api/...")` directly. Rather than hunting down every
 * call site (and risking missing new ones later), patch the globals once
 * the base is known so a relative "/api/..." path transparently resolves
 * against the backend origin in production too. A no-op in dev, where
 * base is "".
 */
let globalsPatched = false;
function patchGlobalsForBase(base: string): void {
  if (
    globalsPatched ||
    typeof window === "undefined" ||
    !base ||
    typeof window.fetch !== "function" ||
    typeof window.EventSource !== "function"
  ) {
    return;
  }
  globalsPatched = true;

  const originalFetch = window.fetch.bind(window);
  window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    if (typeof input === "string" && input.startsWith("/api/")) {
      return originalFetch(`${base}${input}`, init);
    }
    return originalFetch(input, init);
  }) as typeof window.fetch;

  const OriginalEventSource = window.EventSource;
  window.EventSource = class extends OriginalEventSource {
    constructor(url: string | URL, eventSourceInitDict?: EventSourceInit) {
      const resolvedUrl = typeof url === "string" && url.startsWith("/api/") ? `${base}${url}` : url;
      super(resolvedUrl, eventSourceInitDict);
    }
  };
}

/**
 * Resolve (and cache) the base URL to prepend to API paths.
 *
 * Returns `""` in dev mode so relative URLs work through the Vite proxy.
 * Returns `"http://127.0.0.1:<port>"` in Tauri production builds.
 */
export async function resolveBackendBase(): Promise<string> {
  if (resolvedBase !== null) return resolvedBase;
  if (resolution) return resolution;

  if (isDev() || !isTauri()) {
    resolvedBase = "";
    return resolvedBase;
  }

  resolution = (async () => {
    const [{ listen }, { invoke }] = await Promise.all([
      import("@tauri-apps/api/event"),
      import("@tauri-apps/api/core"),
    ]);

    return new Promise<string>((resolve, reject) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (!settled) {
          settled = true;
          reject(new Error(`Backend did not signal ready within ${HANDSHAKE_TIMEOUT_MS} ms`));
        }
      }, HANDSHAKE_TIMEOUT_MS);

      const settle = (port: number) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolvedBase = `http://127.0.0.1:${port}`;
        patchGlobalsForBase(resolvedBase);
        resolve(resolvedBase);
      };

      // Attach listener first so we never miss the event.
      listen<{ port: number }>("backend-ready", (event) => {
        settle(event.payload.port);
      }).catch((err) => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          reject(err);
        }
      });

      // Also ask the Rust side in case the event already fired before we
      // attached the listener. Both paths are idempotent via `settled`.
      invoke<number | null>("get_backend_port")
        .then((port) => {
          if (typeof port === "number") settle(port);
        })
        .catch(() => {
          // Command unavailable — fine, we're still waiting on the event.
        });
    });
  })();

  return resolution;
}

/**
 * Synchronous accessor for already-resolved base. Returns null until the
 * async resolution has completed at least once. Callers that need the
 * base during app bootstrap should await `resolveBackendBase()` first.
 */
export function getBackendBase(): string | null {
  return resolvedBase;
}

/** Test-only: forget the cached base so the next resolve() redoes the work. */
export function __resetBackendBaseForTests(): void {
  resolvedBase = null;
  resolution = null;
}
