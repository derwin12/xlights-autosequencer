import React from 'react';
import styles from './Splash.module.css';

/**
 * Rendered between the Tauri window opening and the backend sidecar
 * signalling `backend-ready`. Covers FR-009: "MUST either start within a
 * reasonable time using bundled assets, or clearly communicate any
 * one-time setup progress (download, extraction) with visible status —
 * not present a silent or unresponsive window."
 */
export function Splash({ error }: { error?: string }) {
  return (
    <div className={styles.splash} data-testid="splash-screen">
      <div className={styles.logo}>xLightsAI</div>
      {error ? (
        <div className={styles.error}>
          <p className={styles.errorTitle}>Backend didn't start</p>
          <p className={styles.errorDetail}>{error}</p>
          <p className={styles.errorHint}>
            Try relaunching the app. If the problem persists, see the
            support page for diagnostic steps.
          </p>
        </div>
      ) : (
        <>
          <div className={styles.spinner} aria-hidden="true" />
          <div className={styles.message}>Starting up…</div>
        </>
      )}
    </div>
  );
}
