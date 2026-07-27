import React, { useEffect, useState } from "react";
import styles from "./About.module.css";
import { useManifestStore } from "../../store/manifest";
import { isBackendStale, isUpdateAvailable } from "../../lib/manifestStaleness";

/**
 * About dialog — version label, build details, credits, link to the
 * download page so users can pull newer releases manually.
 *
 * Covers FR-011 (version discovery + update path) and US4 acceptance
 * scenarios. Auto-update is explicitly out of scope for v1.
 */

const DOWNLOAD_PAGE_URL = "https://github.com/derwin12/xlights-autosequencer/releases";
const ORIGINAL_IDEA_URL = "https://github.com/bobbyfriday/xlight-autosequencer";
export const FACEBOOK_GROUP_URL = "https://www.facebook.com/groups/xlightsai";

export function isTauri(): boolean {
  return typeof window !== "undefined" && Boolean((window as any).__TAURI_INTERNALS__ || (window as any).__TAURI__);
}

export async function openExternal(url: string) {
  try {
    const { open } = await import("@tauri-apps/plugin-shell");
    await open(url);
  } catch {
    window.open(url, "_blank");
  }
}

/** Reveal backend.log's folder in Explorer -- packaged app only. Dev mode's
 * backend prints straight to the terminal that launched it, so there's no
 * log file to open. */
async function openLogsFolder(): Promise<void> {
  const [{ invoke }, { open }] = await Promise.all([
    import("@tauri-apps/api/core"),
    import("@tauri-apps/plugin-shell"),
  ]);
  const dir = await invoke<string>("get_log_dir");
  await open(dir);
}

/** Open ReleaseNotes.txt (bundled as a resource next to the exe, see
 * tauri.conf.json's bundle.resources) with the OS's default text viewer --
 * packaged app only, there's nothing bundled to resolve in dev mode. */
async function openReleaseNotes(): Promise<void> {
  const [{ resolveResource }, { open }] = await Promise.all([
    import("@tauri-apps/api/path"),
    import("@tauri-apps/plugin-shell"),
  ]);
  const path = await resolveResource("ReleaseNotes.txt");
  await open(path);
}

/** Full 40-char hashes (bundled manifests) are trimmed; short dev hashes
 * keep their "-dirty" suffix intact. */
export function shortCommit(commit: string): string {
  return commit.length > 16 ? commit.slice(0, 10) : commit;
}

export function About({ open, onClose }: { open: boolean; onClose: () => void }) {
  const manifest = useManifestStore((s) => s.manifest);
  const load = useManifestStore((s) => s.load);
  // Neither openLogsFolder nor openReleaseNotes previously surfaced errors --
  // their buttons were fired with `void fn()`, so an invoke()/open() failure
  // (e.g. no logs written yet, resource not found) silently vanished as an
  // unhandled promise rejection with nothing shown in the UI (user report,
  // 2026-07-26/27: "Open Logs folder doesn't appear to do anything").
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (open) { void load(); setActionError(null); }
  }, [open, load]);

  async function runAction(fn: () => Promise<void>) {
    setActionError(null);
    try {
      await fn();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  }

  if (!open) return null;

  const backendStale = isBackendStale(manifest?.backend_commit, manifest?.repo_head_commit);
  const updateAvailable = isUpdateAvailable(
    manifest?.repo_head_commit, manifest?.origin_main_commit, manifest?.origin_ahead_of_head,
  );

  return (
    <div className={styles.backdrop} role="dialog" aria-modal="true" onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={styles.title}>xLightsAI</h2>
        <div className={styles.version}>
          {manifest?.app_version ?? "…"}
          {manifest?.target_arch ? ` · ${manifest.target_arch}` : null}
        </div>

        {manifest?.build_timestamp && (
          <div className={styles.buildTs}>Built {manifest.build_timestamp}</div>
        )}

        <div className={styles.links}>
          <button
            className={styles.linkBtn}
            onClick={() => void openExternal(DOWNLOAD_PAGE_URL)}
          >
            Check for updates
          </button>
          <button
            className={styles.linkBtn}
            onClick={() => void openExternal(FACEBOOK_GROUP_URL)}
          >
            Join the Facebook group
          </button>
          {isTauri() && (
            <button
              className={styles.linkBtn}
              onClick={() => void runAction(openReleaseNotes)}
            >
              Release notes
            </button>
          )}
          {isTauri() && (
            <button
              className={styles.linkBtn}
              onClick={() => void runAction(openLogsFolder)}
            >
              Open logs folder
            </button>
          )}
        </div>

        {actionError && (
          <div className={styles.staleWarning}>⚠ {actionError}</div>
        )}

        {manifest?.bundled_vamp_plugins && manifest.bundled_vamp_plugins.length > 0 && (
          <div className={styles.credits}>
            <h3>Bundled Vamp plugin packs</h3>
            <ul>
              {manifest.bundled_vamp_plugins.map((name) => (
                <li key={name}>{name}</li>
              ))}
            </ul>
            <p className={styles.license}>
              Vamp plugins are distributed under GPL/LGPL licenses.
              Stem separation weights (htdemucs_6s) are CC BY-NC 4.0 and
              are downloaded on first use; see the demucs repo for full
              terms.
            </p>
          </div>
        )}

        {(manifest?.frontend_commit || manifest?.backend_commit) && (
          <div className={styles.commits}>
            {manifest?.frontend_commit && (
              <div>frontend: <code>{manifest.frontend_commit.slice(0, 10)}</code></div>
            )}
            {manifest?.backend_commit && (
              <div>backend: <code>{shortCommit(manifest.backend_commit)}</code></div>
            )}
            {manifest?.repo_head_commit && (
              <div>local checkout: <code>{shortCommit(manifest.repo_head_commit)}</code></div>
            )}
            {manifest?.origin_main_commit && (
              <div>origin/main: <code>{shortCommit(manifest.origin_main_commit)}</code></div>
            )}
            {manifest?.backend_started_at && (
              <div>backend up since: <code>{manifest.backend_started_at}</code></div>
            )}
            {updateAvailable && (
              <div className={styles.staleWarning}>
                ⚠ origin/main has commits this checkout hasn't pulled yet — run <code>git pull</code>.
              </div>
            )}
            {!updateAvailable && backendStale && (
              <div className={styles.staleWarning}>
                ⚠ code was pulled since the backend started — restart the server to pick it up.
              </div>
            )}
          </div>
        )}

        <div className={styles.credit}>
          Maintained by DarylE. Original idea from{" "}
          <button
            className={styles.creditLink}
            onClick={() => void openExternal(ORIGINAL_IDEA_URL)}
          >
            bobbyfriday
          </button>
          .
        </div>

        <div className={styles.actions}>
          <button className={styles.btnPrimary} onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
