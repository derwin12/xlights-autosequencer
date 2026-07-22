import { useRef, useState } from 'react';
import styles from './LayoutUpload.module.css';

export interface ActiveLayout {
  layout_id: string;
  display_name?: string;
  props?: unknown[];
  total_pixels?: number;
  imported_at?: string;
  xml_path?: string;
  is_uploaded: boolean;
}

interface LayoutUploadProps {
  /** Called with the new active layout after a successful upload, or after
   * a delete (the reverted-to committed layout, or null if none exists). */
  onLayoutChange: (layout: ActiveLayout | null) => void;
  /** Compact renders just the upload controls (no explanatory heading),
   * for embedding under an existing layout summary rather than as the
   * only content on screen. */
  compact?: boolean;
  /** Show the "Revert to Repo Layout" button — only meaningful when the
   * currently active layout is an uploaded override. */
  showRemove?: boolean;
}

/**
 * Lets a user override the layout xOnset generates against with their own
 * xlights_rgbeffects.xml, instead of only the repo-committed one. Stored
 * outside the git checkout (~/.xlight/layout/) so it survives `git pull`.
 */
export function LayoutUpload({ onLayoutChange, compact = false, showRemove = false }: LayoutUploadProps) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rgbeffectsRef = useRef<HTMLInputElement>(null);
  const networksRef = useRef<HTMLInputElement>(null);

  async function handleUpload() {
    const rgbeffectsFile = rgbeffectsRef.current?.files?.[0];
    if (!rgbeffectsFile) {
      setError('Choose an xlights_rgbeffects.xml file first');
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('rgbeffects', rgbeffectsFile);
      const networksFile = networksRef.current?.files?.[0];
      if (networksFile) form.append('networks', networksFile);

      const res = await fetch('/api/v1/layout', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || 'Upload failed');
      onLayoutChange(data);
      if (rgbeffectsRef.current) rgbeffectsRef.current.value = '';
      if (networksRef.current) networksRef.current.value = '';
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  }

  async function handleRemove() {
    setUploading(true);
    setError(null);
    try {
      const res = await fetch('/api/v1/layout', { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || 'Remove failed');
      onLayoutChange(data?.layout_id ? data : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Remove failed');
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className={compact ? styles.compact : styles.root} data-testid="layout-upload">
      {!compact && (
        <>
          <h3 className={styles.title}>Upload Your Layout</h3>
          <p className={styles.hint}>
            Use your own show's <code>xlights_rgbeffects.xml</code> (and
            optionally <code>xlights_networks.xml</code>) instead of the
            one committed to this repo checkout. Stored outside the repo —
            it survives a <code>git pull</code>.
          </p>
        </>
      )}

      <div className={styles.fields}>
        <label className={styles.fileLabel}>
          xlights_rgbeffects.xml
          <input
            ref={rgbeffectsRef}
            type="file"
            accept=".xml"
            data-testid="layout-upload-rgbeffects"
            disabled={uploading}
          />
        </label>
        <label className={styles.fileLabel}>
          xlights_networks.xml <span className={styles.optional}>(optional)</span>
          <input
            ref={networksRef}
            type="file"
            accept=".xml"
            data-testid="layout-upload-networks"
            disabled={uploading}
          />
        </label>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.actions}>
        <button
          className={styles.uploadBtn}
          onClick={handleUpload}
          disabled={uploading}
          data-testid="layout-upload-submit"
        >
          {uploading ? 'Uploading…' : 'Upload Layout'}
        </button>
        {showRemove && (
          <button
            className={styles.removeBtn}
            onClick={handleRemove}
            disabled={uploading}
            data-testid="layout-upload-remove"
          >
            Revert to Repo Layout
          </button>
        )}
      </div>
    </div>
  );
}
