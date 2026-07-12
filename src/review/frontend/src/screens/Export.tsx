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

// Known render stages, in pipeline order (src/review/api/v1/export.py).
// Stages the backend emits that aren't listed here are appended on the fly,
// so new backend stages show up without a frontend change.
const RENDER_STAGES: { id: string; label: string }[] = [
  { id: 'building_plan', label: 'building plan' },
  { id: 'placing_effects', label: 'placing effects' },
  { id: 'writing_xml', label: 'writing xml' },
];

type StageStatus = 'pending' | 'running' | 'done' | 'failed';

interface RenderLogLine {
  text: string;
  kind: 'info' | 'ok' | 'err' | 'progress';
}

export function Export({ song, layoutId, layoutXmlPath, onExportComplete, onLayoutImported }: ExportProps) {
  const [exporting, setExporting] = useState(false);
  const [outputPath, setOutputPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Render-progress panels (stage list + stream log), populated from the
  // export SSE. stageOrder holds known stages plus any new ones the backend
  // emits; stageStatus tracks each stage's lifecycle.
  const [stageOrder, setStageOrder] = useState<{ id: string; label: string }[]>(RENDER_STAGES);
  const [stageStatus, setStageStatus] = useState<Record<string, StageStatus>>({});
  const [renderLog, setRenderLog] = useState<RenderLogLine[]>([]);
  const renderLogRef = useRef<HTMLDivElement>(null);
  const renderStartRef = useRef<number | null>(null);
  const runningStageRef = useRef<string | null>(null);
  const [progressPct, setProgressPct] = useState(0);
  const [elapsedMs, setElapsedMs] = useState(0);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function stopElapsedTimer() {
    if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
    if (renderStartRef.current != null) {
      setElapsedMs(Date.now() - renderStartRef.current);
    }
  }

  useEffect(() => () => {
    if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
  }, []);
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

  // Auto-scroll the stream log
  useEffect(() => {
    if (renderLogRef.current) {
      renderLogRef.current.scrollTop = renderLogRef.current.scrollHeight;
    }
  }, [renderLog.length]);

  function pushLog(line: RenderLogLine) {
    setRenderLog((prev) => [...prev, line]);
  }

  function elapsedSec(): string {
    const start = renderStartRef.current;
    return start != null ? `${Math.round((Date.now() - start) / 1000)}s` : '0s';
  }

  async function handleRender() {
    setError(null);
    setExporting(true);
    setStageOrder(RENDER_STAGES);
    setStageStatus({});
    setRenderLog([{ text: `› render: ${song.title}`, kind: 'info' }]);
    setProgressPct(0);
    setElapsedMs(0);
    renderStartRef.current = Date.now();
    if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
    elapsedTimerRef.current = setInterval(() => {
      if (renderStartRef.current != null) {
        setElapsedMs(Date.now() - renderStartRef.current);
      }
    }, 250);
    try {
      const res = await fetch(`/api/v1/songs/${song.song_id}/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format: 'xsq' }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Export failed');
        setExporting(false);
        stopElapsedTimer();
        return;
      }
      // Stream stage progress
      const es = new EventSource(`/api/v1/songs/${song.song_id}/export/status`);
      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          const stage: string | undefined = data.stage;
          if (!stage) return;

          if (stage === 'done') {
            const running = runningStageRef.current;
            if (running) {
              setStageStatus((prev) => ({ ...prev, [running]: 'done' }));
              pushLog({ text: `✓ ${running.replace(/_/g, ' ')}`, kind: 'ok' });
              runningStageRef.current = null;
            }
            pushLog({ text: `✓ done · ${elapsedSec()}`, kind: 'ok' });
            pushLog({ text: `  → ${data.output_path}`, kind: 'ok' });
            setOutputPath(data.output_path);
            setProgressPct(100);
            onExportComplete?.(data.output_path);
            setExporting(false);
            stopElapsedTimer();
            es.close();
          } else if (stage === 'failed') {
            const running = runningStageRef.current;
            if (running) {
              setStageStatus((prev) => ({ ...prev, [running]: 'failed' }));
              runningStageRef.current = null;
            }
            pushLog({ text: `✗ ${data.error ?? 'Export failed'}`, kind: 'err' });
            setError(data.error ?? 'Export failed');
            setExporting(false);
            stopElapsedTimer();
            es.close();
          } else {
            // A pipeline stage started: previous running stage is done.
            setStageOrder((prev) =>
              prev.some((s) => s.id === stage)
                ? prev
                : [...prev, { id: stage, label: stage.replace(/_/g, ' ') }],
            );
            const prevRunning = runningStageRef.current;
            if (prevRunning && prevRunning !== stage) {
              setStageStatus((prev) => ({ ...prev, [prevRunning]: 'done' }));
              pushLog({ text: `✓ ${prevRunning.replace(/_/g, ' ')}`, kind: 'ok' });
            }
            runningStageRef.current = stage;
            setStageStatus((prev) => ({ ...prev, [stage]: 'running' }));
            pushLog({ text: `› ${stage.replace(/_/g, ' ')}: running…`, kind: 'info' });
            if (typeof data.progress === 'number') {
              setProgressPct(Math.round(data.progress * 100));
              pushLog({
                text: `  ${Math.round(data.progress * 100)}% · ${elapsedSec()}`,
                kind: 'progress',
              });
            }
          }
        } catch {}
      };
      es.onerror = () => {
        es.close();
        setExporting(false);
        stopElapsedTimer();
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
      setExporting(false);
      stopElapsedTimer();
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

      {!outputPath && (
        <button
          className={styles.renderBtn}
          onClick={handleRender}
          disabled={exporting}
        >
          {exporting ? 'Rendering…' : 'Render Sequence'}
        </button>
      )}

      {renderLog.length > 0 && (
        <>
        <div data-testid="render-phase-strip" className={styles.phaseStrip}>
          {stageOrder.map((stage, i) => {
            const status: StageStatus = stageStatus[stage.id] ?? 'pending';
            const isDone = status === 'done';
            const isActive = status === 'running';
            const isFailed = status === 'failed';
            const fillPct = isDone ? 100 : isActive ? progressPct : 0;
            return (
              <div
                key={stage.id}
                className={[
                  styles.phaseCard,
                  isDone ? styles.phaseCardDone : '',
                  isActive ? styles.phaseCardActive : '',
                  isFailed ? styles.phaseCardFailed : '',
                  status === 'pending' ? styles.phaseCardPending : '',
                ].join(' ')}
              >
                <div className={styles.phaseCardInner}>
                  <span className={[
                    styles.phaseGlyph,
                    isDone ? styles.phaseGlyphDone
                    : isActive ? styles.phaseGlyphActive
                    : isFailed ? styles.phaseGlyphFailed
                    : styles.phaseGlyphPending,
                  ].join(' ')}>
                    {isDone ? '✓' : isActive ? '●' : isFailed ? '✗' : String(i + 1).padStart(2, '0')}
                  </span>
                  <span className={[styles.phaseLabel, isActive ? styles.phaseLabelActive : ''].join(' ')}>
                    {stage.label}
                  </span>
                </div>
                <div className={styles.phaseBar}>
                  <i
                    className={styles.phaseBarFill}
                    style={{
                      width: `${fillPct}%`,
                      background: isFailed ? 'var(--err, #d43a2f)' : 'var(--ok, #4ade80)',
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <div data-testid="render-progress" className={styles.progressGrid}>
          <div className={styles.stagePanel}>
            <div className={styles.panelHeader}>
              stages · {Object.values(stageStatus).filter((s) => s === 'done').length} / {stageOrder.length} done
            </div>
            <div className={styles.stageList}>
              {stageOrder.map((stage) => {
                const status: StageStatus = stageStatus[stage.id] ?? 'pending';
                const glyph =
                  status === 'done' ? '✓'
                  : status === 'running' ? '●'
                  : status === 'failed' ? '✗'
                  : '○';
                const glyphClass =
                  status === 'done' ? styles.glyphDone
                  : status === 'running' ? styles.glyphRunning
                  : status === 'failed' ? styles.glyphFailed
                  : styles.glyphPending;
                return (
                  <div
                    key={stage.id}
                    data-testid={`render-stage-${stage.id}`}
                    data-status={status}
                    className={[
                      styles.stageRow,
                      status === 'running' ? styles.stageRunning : '',
                      status === 'pending' ? styles.stagePending : '',
                    ].join(' ')}
                  >
                    <span className={`${styles.stageGlyph} ${glyphClass}`}>{glyph}</span>
                    <span className={styles.stageName}>{stage.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
          <div className={styles.consolePanel}>
            <div className={styles.panelHeader}>stream · {renderLog.length} lines</div>
            <div ref={renderLogRef} className={styles.consoleBody}>
              {renderLog.map((line, i) => (
                <div
                  key={i}
                  className={[
                    styles.logLine,
                    line.kind === 'ok' ? styles.logOk : '',
                    line.kind === 'err' ? styles.logErr : '',
                    line.kind === 'progress' ? styles.logProgress : '',
                  ].join(' ')}
                >
                  {line.text}
                </div>
              ))}
              {exporting && <span className={styles.cursor}>▍</span>}
            </div>
          </div>
          <div data-testid="render-inspector" className={styles.inspector}>
            <div className={styles.inspectorHeader}>
              <span>render</span>
              <span className={error ? styles.statusFailed : outputPath ? styles.statusDone : styles.statusLive}>
                {error ? '✗ failed' : outputPath ? '✓ done' : '● live'}
              </span>
            </div>
            <div className={styles.inspectorProgress}>
              <div className={styles.inspectorPctRow}>
                <span
                  className={styles.inspectorPct}
                  style={{ color: error ? 'var(--err, #d43a2f)' : 'var(--accent, #4ade80)' }}
                >
                  {progressPct}%
                </span>
                <span className={styles.inspectorTime}>{Math.round(elapsedMs / 1000)}s</span>
              </div>
              <div className={styles.inspectorBar}>
                <i
                  className={styles.inspectorBarFill}
                  style={{
                    width: `${progressPct}%`,
                    background: error ? 'var(--err, #d43a2f)' : 'var(--accent, #4ade80)',
                  }}
                />
              </div>
              <div className={styles.inspectorPhaseLabel}>
                {error ? 'failed'
                  : outputPath ? 'complete'
                  : (stageOrder.find((s) => stageStatus[s.id] === 'running')?.label ?? 'starting…')}
              </div>
            </div>
            <div className={styles.inspectorSection}>
              <div className={styles.inspectorSectionHeader}>result</div>
              {[
                { key: 'effect plan', done: stageStatus['building_plan'] === 'done' },
                { key: 'effects placed', done: stageStatus['placing_effects'] === 'done' },
                { key: 'xsq written', done: stageStatus['writing_xml'] === 'done' },
                { key: 'output file', done: outputPath != null },
              ].map((row) => (
                <div key={row.key} className={styles.resultRow}>
                  <span className={row.done ? styles.resultGlyphHas : styles.resultGlyphNot}>
                    {row.done ? '✓' : '·'}
                  </span>
                  <span className={row.done ? styles.resultKey : styles.resultKeyDim}>{row.key}</span>
                </div>
              ))}
              {outputPath && (
                <>
                  <div className={styles.resultFile}>{outputPath.split('/').pop()}</div>
                  <a
                    className={styles.inspectorDownload}
                    href={`/api/v1/songs/${song.song_id}/export/download`}
                    download
                  >
                    Download .xsq
                  </a>
                </>
              )}
            </div>
          </div>
        </div>
        </>
      )}
    </div>
  );
}
