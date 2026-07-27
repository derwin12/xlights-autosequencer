/**
 * Thin wrapper over Tauri's dialog plugin that falls back to browser
 * file inputs / anchor downloads in dev mode.
 *
 * In Tauri production:
 *   - `openAudio()` calls `tauri.dialog.open` with an audio filter and
 *     returns absolute file paths the backend can read directly via
 *     POST /api/v1/import/by-path.
 *   - `saveSequence()` calls `tauri.dialog.save` and returns the
 *     chosen destination absolute path.
 *   - `onDrop()` listens for Tauri's file-drop event.
 *
 * In Vite dev mode:
 *   - `openAudio()` triggers a hidden `<input type="file">` and returns
 *     pseudo-paths (the browser only exposes File objects). The caller
 *     must then fall back to the existing multipart-upload flow.
 *   - `saveSequence()` returns a placeholder path; caller should fall
 *     back to browser download.
 *   - `onDrop()` attaches a dragover+drop listener to window.
 */

import { apiFetch } from "./apiClient";

const AUDIO_EXTENSIONS = ["mp3", "wav", "flac", "aiff", "aif", "m4a"];

export function isTauri(): boolean {
  return typeof window !== "undefined" &&
    Boolean((window as any).__TAURI_INTERNALS__ || (window as any).__TAURI__);
}

export interface OpenAudioResult {
  paths: string[];
  /** True when the result contains real absolute paths (Tauri mode). */
  usable: boolean;
  /** Dev-only: the browser File objects, since there's no path. */
  files?: File[];
}

/** Present a native Open dialog for audio files. */
export async function openAudio(opts?: { multiple?: boolean; title?: string }): Promise<OpenAudioResult> {
  if (isTauri()) {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const result = await open({
      multiple: opts?.multiple ?? true,
      title: opts?.title ?? "Choose audio files",
      filters: [{ name: "Audio", extensions: AUDIO_EXTENSIONS }],
    });
    const paths = result === null ? [] : Array.isArray(result) ? result : [result];
    return { paths, usable: true };
  }
  // Browser fallback.
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = AUDIO_EXTENSIONS.map((e) => `.${e}`).join(",");
    if (opts?.multiple) input.multiple = true;
    input.onchange = () => {
      const files = input.files ? Array.from(input.files) : [];
      resolve({
        paths: files.map((f) => `browser://${f.name}`),
        usable: false,
        files,
      });
    };
    input.click();
  });
}

/** Present a native Save dialog for a generated .xsq file. */
export async function saveSequence(opts?: { defaultName?: string; title?: string }): Promise<string | null> {
  if (isTauri()) {
    const { save } = await import("@tauri-apps/plugin-dialog");
    const result = await save({
      defaultPath: opts?.defaultName ?? "output.xsq",
      title: opts?.title ?? "Save xLights sequence",
      filters: [{ name: "xLights sequence", extensions: ["xsq"] }],
    });
    return result ?? null;
  }
  // Dev fallback: no save dialog — caller should fall back to browser
  // download flow.
  return null;
}

/** Listen for files dropped onto the app window. */
export type DropUnsubscribe = () => void;

export async function onDrop(callback: (paths: string[]) => void): Promise<DropUnsubscribe> {
  if (isTauri()) {
    const { getCurrentWebview } = await import("@tauri-apps/api/webview");
    // Tauri 2's DragDropEvent is a discriminated union keyed by `type`
    // ('enter' | 'over' | 'drop' | 'leave') -- only 'enter' and 'drop'
    // carry `paths`. The previous implementation treated the whole
    // event.payload as a bare string[] (a holdover from Tauri 1's
    // `tauri://file-drop`, which really was just paths), so it silently
    // passed the wrong shape to every caller and this listener was never
    // actually wired into the UI to catch it (2026-07-26 bug report:
    // dropping audio/video onto the packaged app did nothing, only the
    // file picker worked).
    const unlisten = await getCurrentWebview().onDragDropEvent((event) => {
      if (event.payload.type === "drop") {
        callback(event.payload.paths);
      }
    });
    return unlisten;
  }
  // Browser fallback.
  const handler = (e: DragEvent) => {
    e.preventDefault();
    const paths: string[] = [];
    if (e.dataTransfer?.files) {
      for (const f of Array.from(e.dataTransfer.files)) {
        paths.push(`browser://${f.name}`);
      }
    }
    callback(paths);
  };
  const dragover = (e: DragEvent) => e.preventDefault();
  window.addEventListener("drop", handler);
  window.addEventListener("dragover", dragover);
  return () => {
    window.removeEventListener("drop", handler);
    window.removeEventListener("dragover", dragover);
  };
}

/** Import a file-by-path via the packaged-app-only backend endpoint. */
export async function importByPath(path: string, folderId?: string): Promise<unknown> {
  const r = await apiFetch("/api/v1/import/by-path", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, folder_id: folderId }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err?.error?.message ?? `Import failed: HTTP ${r.status}`);
  }
  return r.json();
}

/** Save the most recent export result to a user-chosen path. */
export async function saveExportTo(songId: string, path: string): Promise<void> {
  const r = await apiFetch(`/api/v1/songs/${songId}/export/save-to`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err?.error?.message ?? `Save failed: HTTP ${r.status}`);
  }
}
