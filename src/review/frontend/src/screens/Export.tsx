import React, { useEffect, useRef, useState } from 'react';
import styles from './Export.module.css';

interface Song {
  song_id: string;
  title: string;
  status: string;
  duration_ms: number;
}

interface ExportProps {
  song: Song;
  layoutId: string | null;
  layoutXmlPath?: string | null;
  onExportComplete?: (outputPath: string) => void;
  onLayoutImported?: (layoutId: string, xmlPath: string) => void;
}

export function Export({ song, layoutId, layoutXmlPath, onExportComplete, onLayoutImported }: ExportProps) {
  const [exporting, setExporting] = useState(false);
  const [outputPath, setOutputPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importingLayout, setImportingLayout] = useState(false);
  const [layoutError, setLayoutError] = useState<string | null>(null);
  const layoutInputRef = useRef<HTMLInputElement>(null);

  // Details of the currently-stored layout, shown so the user always sees —
  // and can replace — which rgbeffects file a render will target (rather
  // than silently reusing whatever was imported in an earlier session).
  const [layoutInfo, setLayoutInfo] = useState<{
    display_name?: string;
    props?: unknown[];
    imported_at?: string;
  } | null>(null);

  const isThemed = song.status === 'themed';
  // A layout imported before file persistence was added has a layoutId but
  // no xml_path on disk — treat that the same as "no layout" so re-import
  // stays reachable instead of only surfacing as an export-time failure.
  const hasLayout = layoutId != null && layoutXmlPath != null;
  const needsReimport = layoutId != null && layoutXmlPath == null;

  useEffect(() => {
    if (layoutId == null) return;
    fetch('/api/v1/layout')
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        if (body) setLayoutInfo(body);
      })
      .catch(() => {});
  }, [layoutId, layoutXmlPath]);

  async function handleLayoutFile(file: File) {
    setLayoutError(null);
    setImportingLayout(true);
    try {
      const formData = new FormData();
      formData.append('layout_xml', file);

      const res = await fetch('/api/v1/layout', {
        method: 'POST',
        body: formData,
      });

      const body = await res.json();
      if (!res.ok) {
        setLayoutError(body?.error?.message ?? 'Layout import failed');
        return;
      }

      onLayoutImported?.(body.layout.layout_id, body.layout.xml_path);
    } catch (err) {
      setLayoutError(err instanceof Error ? err.message : 'Layout import failed');
    } finally {
      setImportingLayout(false);
    }
  }

  function handleLayoutInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleLayoutFile(file);
  }

  async function handleRender() {
    setError(null);
    setExporting(true);
    try {
      const res = await fetch(`/api/v1/songs/${song.song_id}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format: 'xsq' }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Export failed');
        return;
      }
      // Poll SSE for completion
      const es = new EventSource(`/api/v1/songs/${song.song_id}/export/status`);
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.stage === 'done') {
            setOutputPath(data.output_path);
            onExportComplete?.(data.output_path);
            es.close();
          } else if (data.stage === 'failed') {
            setError(data.error ?? 'Export failed');
            es.close();
          }
        } catch {}
      };
      es.onerror = () => {
        es.close();
        setExporting(false);
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setExporting(false);
    }
  }

  const isSourceMissing = song.status === 'source_missing';

  if (isSourceMissing) {
    return (
      <div data-testid="source-missing-block" className={styles.block}>
        <h3>Audio File Missing</h3>
        <p>The audio file for <strong>{song.title}</strong> can no longer be found.</p>
        <p>Use "Locate file" to point to the audio file on your disk.</p>
      </div>
    );
  }

  if (!hasLayout) {
    return (
      <div data-testid="layout-required" className={styles.block}>
        <h3>Layout Required</h3>
        {needsReimport ? (
          <p>
            This layout was imported before file persistence was added.
            Re-import your <code>xlights_rgbeffects.xml</code> below, then
            try exporting again.
          </p>
        ) : (
          <p>Import your <code>xlights_rgbeffects.xml</code> to continue.</p>
        )}
        <input
          data-testid="layout-file-input"
          ref={layoutInputRef}
          type="file"
          accept=".xml"
          style={{ display: 'none' }}
          onChange={handleLayoutInputChange}
        />
        <button
          className={styles.layoutBtn}
          onClick={() => layoutInputRef.current?.click()}
          disabled={importingLayout}
        >
          {importingLayout ? 'Importing…' : 'Import Layout'}
        </button>
        {layoutError && (
          <p data-testid="layout-error-message" className={styles.error}>{layoutError}</p>
        )}
      </div>
    );
  }

  if (!isThemed) {
    return (
      <div data-testid="incomplete-theming" className={styles.block}>
        <h3>Theming Incomplete</h3>
        <p>All sections must be themed before exporting.</p>
      </div>
    );
  }

  return (
    <div data-testid="export-form" className={styles.root}>
      <h2 className={styles.title}>Export: {song.title}</h2>

      <div data-testid="layout-summary" style={{ marginBottom: 16 }}>
        <p style={{ margin: '0 0 8px', color: 'var(--color-text-muted, #888)', fontSize: 13 }}>
          Layout: <strong style={{ color: 'var(--color-text, #f5f5f0)' }}>
            {layoutInfo?.display_name ?? layoutId}
          </strong>
          {layoutInfo?.props ? ` · ${layoutInfo.props.length} props` : ''}
          {layoutInfo?.imported_at
            ? ` · imported ${new Date(layoutInfo.imported_at).toLocaleDateString()}`
            : ''}
        </p>
        <input
          data-testid="layout-file-input"
          ref={layoutInputRef}
          type="file"
          accept=".xml"
          style={{ display: 'none' }}
          onChange={handleLayoutInputChange}
        />
        <button
          data-testid="layout-replace-btn"
          className={styles.layoutBtn}
          onClick={() => layoutInputRef.current?.click()}
          disabled={importingLayout}
        >
          {importingLayout ? 'Importing…' : 'Replace Layout…'}
        </button>
        {layoutError && (
          <p data-testid="layout-error-message" className={styles.error}>{layoutError}</p>
        )}
      </div>

      {error && <p className={styles.error}>{error}</p>}

      {outputPath ? (
        <div className={styles.success}>
          <p>Export complete!</p>
          <code className={styles.path}>{outputPath}</code>
          <a
            className={styles.downloadBtn}
            href={`/api/v1/songs/${song.song_id}/export/download`}
            download
          >
            Download .xsq
          </a>
        </div>
      ) : (
        <button
          className={styles.renderBtn}
          onClick={handleRender}
          disabled={exporting}
        >
          {exporting ? 'Rendering…' : 'Render Sequence'}
        </button>
      )}
    </div>
  );
}
