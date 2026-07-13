/** Package manifest — loaded once at app start, read from anywhere. */
import { create } from "zustand";
import { apiFetch } from "../lib/apiClient";

export interface Manifest {
  app_version: string;
  build_timestamp: string | null;
  target_arch: string | null;
  frontend_commit: string | null;
  backend_commit: string | null;
  backend_started_at?: string | null;
  bundled_vamp_plugins: string[];
  download_model_manifest_url: string | null;
  is_bundled?: boolean;
}

interface ManifestStore {
  manifest: Manifest | null;
  loading: boolean;
  error: string | null;
  load: () => Promise<void>;
}

export const useManifestStore = create<ManifestStore>((set, get) => ({
  manifest: null,
  loading: false,
  error: null,

  async load() {
    if (get().manifest || get().loading) return;
    set({ loading: true, error: null });
    try {
      const r = await apiFetch("/api/v1/manifest");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = (await r.json()) as Manifest;
      set({ manifest: body, loading: false });
    } catch (err) {
      set({
        loading: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  },
}));
