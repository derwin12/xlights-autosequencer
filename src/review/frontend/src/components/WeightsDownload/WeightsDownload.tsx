import React from "react";
import styles from "./WeightsDownload.module.css";
import { useWeightsDownloadStore } from "../../store/weightsDownload";

/**
 * Modal covering the first-use demucs-weights download.
 *
 * Rendered at app root. Opens itself when the store phase is not `idle`.
 * Displays license note up front (CC BY-NC 4.0) so the user knows the
 * terms before triggering the download.
 */
export function WeightsDownload() {
  const phase = useWeightsDownloadStore((s) => s.phase);
  const status = useWeightsDownloadStore((s) => s.status);
  const overallBytes = useWeightsDownloadStore((s) => s.overallBytes);
  const overallTotal = useWeightsDownloadStore((s) => s.overallTotal);
  const currentShardName = useWeightsDownloadStore((s) => s.currentShardName);
  const errorMessage = useWeightsDownloadStore((s) => s.errorMessage);
  const startDownload = useWeightsDownloadStore((s) => s.startDownload);
  const dismiss = useWeightsDownloadStore((s) => s.dismiss);

  if (phase === "idle") return null;

  const pct = overallTotal > 0 ? Math.min(100, (overallBytes / overallTotal) * 100) : 0;
  const mb = (n: number) => (n / 1024 / 1024).toFixed(1);

  return (
    <div className={styles.backdrop} role="dialog" aria-modal="true">
      <div className={styles.modal} data-testid="weights-download-modal">
        <h2 className={styles.title}>Stem separation model</h2>

        {phase === "prompting" && status && (
          <>
            <p className={styles.body}>
              Stem separation needs a one-time download of
              approximately {mb(status.size_bytes)} MB. Files are stored
              under <code>~/Library/Application Support/xLightsAI/models/</code>
              and will be reused across app updates.
            </p>
            <div className={styles.license}>
              <strong>License:</strong> {status.license || "CC BY-NC 4.0"}
              <p className={styles.licenseNote}>{status.license_note}</p>
            </div>
            <div className={styles.actions}>
              <button className={styles.btnCancel} onClick={dismiss}>
                Cancel
              </button>
              <button className={styles.btnPrimary} onClick={startDownload}>
                Download now
              </button>
            </div>
          </>
        )}

        {phase === "downloading" && (
          <>
            <p className={styles.body}>
              Downloading {currentShardName ?? "weights"}…
            </p>
            <div className={styles.progressTrack}>
              <div
                className={styles.progressBar}
                style={{ width: `${pct}%` }}
                aria-valuenow={pct}
                aria-valuemin={0}
                aria-valuemax={100}
                role="progressbar"
              />
            </div>
            <p className={styles.progressText}>
              {mb(overallBytes)} MB / {mb(overallTotal)} MB ({pct.toFixed(0)}%)
            </p>
          </>
        )}

        {phase === "complete" && (
          <>
            <p className={styles.body}>
              Download complete. You can now run stem separation.
            </p>
            <div className={styles.actions}>
              <button className={styles.btnPrimary} onClick={dismiss}>
                Continue
              </button>
            </div>
          </>
        )}

        {phase === "error" && (
          <>
            <p className={styles.body}>The download did not complete.</p>
            <p className={styles.errorDetail}>{errorMessage}</p>
            <div className={styles.actions}>
              <button className={styles.btnCancel} onClick={dismiss}>
                Close
              </button>
              <button className={styles.btnPrimary} onClick={startDownload}>
                Retry
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
