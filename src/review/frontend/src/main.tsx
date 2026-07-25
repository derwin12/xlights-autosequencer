import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { Splash } from './components/Splash/Splash';
import { bootstrapApi } from './lib/apiClient';

/**
 * Gates rendering of `<App />` on the backend sidecar signalling ready
 * (via `bootstrapApi()` -> `resolveBackendBase()`). Resolves immediately
 * in dev/non-Tauri contexts. Without this gate, `apiFetch` calls made
 * before the backend base URL is known silently fall back to a relative
 * path, which in the packaged app hits the webview's own origin instead
 * of the Flask server and returns the SPA's index.html instead of JSON.
 */
function Root() {
  const [state, setState] = React.useState<{ status: 'loading' | 'ready' | 'error'; error?: string }>({
    status: 'loading',
  });

  React.useEffect(() => {
    let cancelled = false;

    bootstrapApi()
      .then(() => {
        if (!cancelled) setState({ status: 'ready' });
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setState({ status: 'error', error: err instanceof Error ? err.message : String(err) });
        }
      });

    // Only relevant inside the Tauri shell; the dynamic import + listen
    // call are no-ops (and never resolve) in a plain browser dev context.
    let unlisten: (() => void) | undefined;
    if (typeof window !== 'undefined' && ((window as any).__TAURI_INTERNALS__ || (window as any).__TAURI__)) {
      import('@tauri-apps/api/event').then(({ listen }) => {
        Promise.all([
          listen<{ message: string }>('backend-startup-failed', (event) => {
            if (!cancelled) setState({ status: 'error', error: event.payload.message });
          }),
          listen<{ message: string }>('backend-lost', (event) => {
            if (!cancelled) setState({ status: 'error', error: event.payload.message });
          }),
        ]).then((unlisteners) => {
          unlisten = () => unlisteners.forEach((fn) => fn());
        });
      });
    }

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  if (state.status === 'loading') return <Splash />;
  if (state.status === 'error') return <Splash error={state.error} />;
  return <App />;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);
