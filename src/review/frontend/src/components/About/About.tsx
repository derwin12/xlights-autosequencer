import React, { useEffect, useState } from "react";
import styles from "./About.module.css";
import { useManifestStore } from "../../store/manifest";

/**
 * About dialog — version label, build details, credits, link to the
 * download page so users can pull newer releases manually.
 *
 * Covers FR-011 (version discovery + update path) and US4 acceptance
 * scenarios. Auto-update is explicitly out of scope for v1.
 */

const DOWNLOAD_PAGE_URL = "https://github.com/derwin12/xlight-autosequencer/releases";

/** Full 40-char hashes (bundled manifests) are trimmed; short dev hashes
 * keep their "-dirty" suffix intact. */
export function shortCommit(commit: string): string {
  return commit.length > 16 ? commit.slice(0, 10) : commit;
}

export function About({ open, onClose }: { open: boolean; onClose: () => void }) {
  const manifest = useManifestStore((s) => s.manifest);
  const load = useManifestStore((s) => s.load);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  if (!open) return null;
  return (
    <div className={styles.backdrop} role="dialog" aria-modal="true" onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={styles.title}>XLight</h2>
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
            onClick={async () => {
              try {
                const { open } = await import("@tauri-apps/plugin-shell");
                await open(DOWNLOAD_PAGE_URL);
              } catch {
                window.open(DOWNLOAD_PAGE_URL, "_blank");
              }
            }}
          >
            Check for updates
          </button>
        </div>

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
            {manifest?.backend_started_at && (
              <div>backend up since: <code>{manifest.backend_started_at}</code></div>
            )}
          </div>
        )}

        <div className={styles.actions}>
          <button className={styles.btnPrimary} onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
