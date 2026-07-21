import React, { useState } from 'react';
import styles from './XTimingUploadDialog.module.css';

export interface XTimingUploadResult {
  found: boolean;
  word_count: number;
  phoneme_count: number;
  preview: string[];
}

interface XTimingUploadDialogProps {
  songId: string;
  /** Called with the server response after a successful upload. */
  onSaved: (result: XTimingUploadResult) => void;
  onCancel: () => void;
}

/**
 * Lets a user who already has correct word/phoneme timing (typed directly
 * into xLights' own Lyrics timing track, or from another tool) skip
 * WhisperX transcription/alignment entirely for this song — sidesteps the
 * all-or-nothing lyrics-mismatch fallback where one bad patch of pasted
 * lyrics can silently discard the whole alignment for "made up" words
 * (see src.analyzer.xtiming_import). Takes effect on the next Analyze run.
 */
export function XTimingUploadDialog({ songId, onSaved, onCancel }: XTimingUploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUpload() {
    if (!file) {
      setError('Choose a .xtiming file first');
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch(`/api/v1/songs/${songId}/lyrics/xtiming`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || 'Uploading xtiming failed');
      onSaved(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Uploading xtiming failed');
      setUploading(false);
    }
  }

  return (
    <div className={styles.overlay}>
      <div role="dialog" aria-modal="true" aria-label="Add xTiming" className={styles.dialog}>
        <h2 className={styles.title}>Add xTiming</h2>
        <p className={styles.subtitle}>
          Upload a .xtiming file with a Lyrics track (words + phonemes) to use
          its timing directly, skipping WhisperX transcription entirely.
        </p>

        <input
          className={styles.fileInput}
          type="file"
          accept=".xtiming"
          aria-label="xTiming file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />

        {error && <p role="alert" className={styles.error}>{error}</p>}

        <div className={styles.actions}>
          <button className={styles.btnCancel} data-testid="xtiming-upload-cancel" onClick={onCancel} disabled={uploading}>
            Cancel
          </button>
          <button className={styles.btnConfirm} data-testid="xtiming-upload-save" onClick={handleUpload} disabled={uploading || !file}>
            {uploading ? 'Uploading…' : 'Upload'}
          </button>
        </div>
      </div>
    </div>
  );
}
