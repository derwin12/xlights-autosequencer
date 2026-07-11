import React, { useCallback, useEffect, useRef, useState } from 'react';
import styles from './Timeline.module.css';
import { Transport } from '../components/Transport/Transport';
import { Waveform } from '../components/Waveform/Waveform';
import { Ruler } from '../components/Ruler/Ruler';
import { SectionStrip } from '../components/SectionStrip/SectionStrip';
import { LyricTrack } from '../components/LyricTrack/LyricTrack';
import { LightsPreview } from '../components/LightsPreview/LightsPreview';
import { AlgoTrack } from '../components/AlgoTrack/AlgoTrack';
import { StemWaveforms } from '../components/StemWaveforms/StemWaveforms';
import { usePlaybackStore } from '../store/playback';
import { useSectionsStore } from '../store/sections';

interface Section {
  index: number;
  start_ms: number;
  end_ms: number;
  kind: string;
  label: string;
}

interface Assignment {
  section_index: number;
  theme_id: string | null;
  overrides: Record<string, number>;
  user_confirmed: boolean;
}

interface Analysis {
  song_id: string;
  detected_sections: Section[];
  peaks: number[];
  beats: { t_ms: number; bar: number; beat: number; extrapolated?: boolean }[];
  bars?: number[];
  half_bars?: number[];
  eighth_notes?: number[];
  impacts?: { t_ms: number; label?: string }[];
  drops?: { t_ms: number; label?: string }[];
  onsets?: Record<string, number[]>;
  section_boundaries?: number[];
  chord_changes?: number[];
  key_changes?: number[];
  lyrics?: { t_ms: number; duration_ms: number; text: string }[];
  value_curves?: Record<string, { fps: number; values: number[] }>;
  detectors: { name: string; library: string; status: string; confidence: number | null; error: string | null; marks?: number; kind?: string }[];
  completed_at: string;
  [key: string]: unknown;
}

interface Song {
  song_id: string;
  title: string;
  status: string;
  duration_ms: number;
  source_paths: string[];
  [key: string]: unknown;
}

interface TimelineProps {
  song: Song;
  analysis: Analysis;
  assignments: Assignment[];
  onNavigateTheme?: () => void;
}

const LIBRARY_COLORS: Record<string, string> = {
  librosa: '#4ade80',
  vamp: '#38bdf8',
  madmom: '#f97316',
  story: '#a78bfa',
  system: '#94a3b8',
};

function getLibraryColor(library: string): string {
  return LIBRARY_COLORS[library] ?? LIBRARY_COLORS['system'];
}

function getDetectorEvents(
  name: string,
  analysis: Analysis,
  _durationMs: number,
  _markCount: number,
): number[] {
  const lower = name.toLowerCase();
  if (lower.includes('beat')) return analysis.beats.map((b) => b.t_ms);
  if (lower.includes('half_bar') || lower.includes('half bar')) return (analysis.half_bars ?? []);
  if (lower.includes('eighth') || lower.includes('8th')) return (analysis.eighth_notes ?? []);
  if (lower.includes('bar')) return (analysis.bars ?? []);
  if (lower.includes('impact') || lower.includes('kick')) return (analysis.impacts ?? []).map((i) => i.t_ms);
  if (lower.includes('drop')) return (analysis.drops ?? []).map((i) => i.t_ms);
  if (lower.includes('segment') || lower.includes('segmentino')) return (analysis.section_boundaries ?? []);
  if (lower.includes('chord')) return (analysis.chord_changes ?? []);
  if (lower.includes('key')) return (analysis.key_changes ?? []);

  // Onset detectors — extract stem from "aubio_onset (drums)" style suffix
  const onsets = analysis.onsets ?? {};
  const stemMatch = name.match(/\(([^)]+)\)/);
  if (stemMatch) {
    const stem = stemMatch[1].toLowerCase();
    if (onsets[stem]?.length) return onsets[stem];
  }
  if (lower.includes('aubio') || lower.includes('onset') || lower.includes('percussion')) {
    return onsets['full_mix'] ?? [];
  }

  // No real timestamps available — return empty rather than fake evenly-spaced marks
  return [];
}

function fmtMs(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function fmtDuration(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Returns the beat entry whose t_ms is <= timeMs (last beat at or before playhead) */
function getCurrentBeat(
  beats: { t_ms: number; bar: number; beat: number }[],
  timeMs: number
): { bar: number; beat: number } | null {
  let result: { bar: number; beat: number } | null = null;
  for (const b of beats) {
    if (b.t_ms <= timeMs) {
      result = { bar: b.bar, beat: b.beat };
    } else {
      break;
    }
  }
  return result;
}

/** Returns the section that contains timeMs */
function getCurrentSection(sections: Section[], timeMs: number): Section | null {
  for (const sec of sections) {
    if (timeMs >= sec.start_ms && timeMs < sec.end_ms) return sec;
  }
  if (sections.length > 0) return sections[sections.length - 1];
  return null;
}

const KIND_COLORS: Record<string, string> = {
  intro: '#38bdf8',
  verse: '#4ade80',
  pre_chorus: '#a78bfa',
  chorus: '#d97757',
  bridge: '#f97316',
  solo: '#facc15',
  outro: '#94a3b8',
  unknown: '#6a6a78',
};

const ZOOM_LEVELS = [1, 2, 4, 8, 16];

export function Timeline({ song, analysis, assignments, onNavigateTheme }: TimelineProps) {
  const { playing, timeMs, play, pause, seekMs } = usePlaybackStore();
  const {
    sections: storeSections,
    editMode,
    selectedIndex: storeSelectedIndex,
    setSections,
    setEditMode,
    setSelectedIndex,
  } = useSectionsStore();

  const [drawerOpen, setDrawerOpen] = useState<boolean>(true);
  const [hiddenDetectors, setHiddenDetectors] = useState<Set<string>>(new Set());
  // Lyrics render as their own dedicated lane (see LyricTrack below), not as
  // a tick-mark row here — it has no matching getDetectorEvents() case.
  const drawerDetectors = analysis.detectors.filter((det) => det.kind !== 'lyrics');
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [viewStartMs, setViewStartMs] = useState<number>(0);
  const [windowPeaks, setWindowPeaks] = useState<number[] | null>(null);
  const [inspectorCollapsed, setInspectorCollapsed] = useState<boolean>(() => {
    try { return localStorage.getItem('xonset.inspectorCollapsed') === '1'; }
    catch { return false; }
  });
  const toggleInspector = () => {
    setInspectorCollapsed((prev) => {
      const next = !prev;
      try { localStorage.setItem('xonset.inspectorCollapsed', next ? '1' : '0'); } catch {}
      return next;
    });
  };
  const waveformAreaRef = useRef<HTMLDivElement>(null);

  const durationMs = song.duration_ms;

  // Compute visible window
  const viewDurationMs = durationMs / zoomLevel;
  const viewEndMs = Math.min(durationMs, viewStartMs + viewDurationMs);

  // Keep playhead in view when playing
  useEffect(() => {
    if (zoomLevel <= 1) return;
    if (timeMs < viewStartMs || timeMs > viewEndMs) {
      const newStart = Math.max(0, Math.min(durationMs - viewDurationMs, timeMs - viewDurationMs * 0.1));
      setViewStartMs(newStart);
    }
  }, [timeMs, zoomLevel, viewStartMs, viewEndMs, viewDurationMs, durationMs]);

  // Zoom-aware peak fetching: when zoomed, request high-res peaks for the window.
  // Debounced by window-key so rapid zoom/pan doesn't fire a request per frame.
  useEffect(() => {
    if (zoomLevel <= 1) {
      setWindowPeaks(null);
      return;
    }
    let cancelled = false;
    const handle = window.setTimeout(() => {
      const startMs = Math.round(viewStartMs);
      const endMs = Math.round(viewEndMs);
      fetch(`/api/v1/songs/${song.song_id}/peaks?start_ms=${startMs}&end_ms=${endMs}&count=2000`)
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (cancelled || !data?.peaks) return;
          // Only apply if the window still matches — stale responses are ignored
          if (Math.round(viewStartMs) === data.start_ms && Math.round(viewEndMs) === data.end_ms) {
            setWindowPeaks(data.peaks);
          }
        })
        .catch(() => {});
    }, 120);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [song.song_id, zoomLevel, viewStartMs, viewEndMs]);

  const handleWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    const rect = waveformAreaRef.current?.getBoundingClientRect();
    if (!rect) return;

    const cursorRatio = (e.clientX - rect.left) / rect.width;
    const cursorMs = viewStartMs + cursorRatio * viewDurationMs;

    const delta = e.deltaY < 0 ? 1 : -1;
    const currentIdx = ZOOM_LEVELS.indexOf(zoomLevel);
    const nextIdx = Math.max(0, Math.min(ZOOM_LEVELS.length - 1, currentIdx + delta));
    const nextZoom = ZOOM_LEVELS[nextIdx];

    if (nextZoom === zoomLevel) return;

    const nextViewDuration = durationMs / nextZoom;
    const nextStart = Math.max(0, Math.min(durationMs - nextViewDuration, cursorMs - cursorRatio * nextViewDuration));
    setZoomLevel(nextZoom);
    setViewStartMs(nextStart);
  }, [zoomLevel, viewStartMs, viewDurationMs, durationMs]);

  function zoomIn() {
    const currentIdx = ZOOM_LEVELS.indexOf(zoomLevel);
    if (currentIdx >= ZOOM_LEVELS.length - 1) return;
    const nextZoom = ZOOM_LEVELS[currentIdx + 1];
    const nextViewDuration = durationMs / nextZoom;
    const center = viewStartMs + viewDurationMs / 2;
    const nextStart = Math.max(0, Math.min(durationMs - nextViewDuration, center - nextViewDuration / 2));
    setZoomLevel(nextZoom);
    setViewStartMs(nextStart);
  }

  function zoomOut() {
    const currentIdx = ZOOM_LEVELS.indexOf(zoomLevel);
    if (currentIdx <= 0) return;
    const nextZoom = ZOOM_LEVELS[currentIdx - 1];
    if (nextZoom === 1) {
      setZoomLevel(1);
      setViewStartMs(0);
      return;
    }
    const nextViewDuration = durationMs / nextZoom;
    const center = viewStartMs + viewDurationMs / 2;
    const nextStart = Math.max(0, Math.min(durationMs - nextViewDuration, center - nextViewDuration / 2));
    setZoomLevel(nextZoom);
    setViewStartMs(nextStart);
  }

  function toggleDetector(name: string) {
    setHiddenDetectors((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  }

  // Seed the store from analysis whenever the song changes. The sections
  // store is a singleton across the app, so switching songs must reset it
  // or the previous song's sections leak through. We key on song.song_id
  // (not storeSections.length) so a user's mid-song edits don't get
  // overwritten by a spurious re-seed from this song's own analysis, but
  // loading a new song always replaces the store wholesale.
  const seededSongIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (seededSongIdRef.current === song.song_id) return;
    seededSongIdRef.current = song.song_id;
    setSelectedIndex(null);
    setEditMode(false);
    setSections(
      analysis.detected_sections.map((s) => ({
        ...s,
        kind: s.kind as 'intro' | 'verse' | 'chorus' | 'solo' | 'bridge' | 'outro' | 'unknown',
      }))
    );
  }, [song.song_id, analysis.detected_sections, setSections, setSelectedIndex, setEditMode]);

  // Use store sections when populated, fall back to analysis
  const liveSections =
    storeSections.length > 0 ? storeSections : analysis.detected_sections;

  const selectedIndex = storeSelectedIndex ?? 0;

  function handlePrevSection() {
    const idx = Math.max(0, selectedIndex - 1);
    setSelectedIndex(idx);
    seekMs(liveSections[idx]?.start_ms ?? 0);
  }

  function handleNextSection() {
    const idx = Math.min(liveSections.length - 1, selectedIndex + 1);
    setSelectedIndex(idx);
    seekMs(liveSections[idx]?.start_ms ?? 0);
  }

  const currentAssignment = assignments.find((a) => a.section_index === selectedIndex);

  // Inspector data
  const currentBeat = getCurrentBeat(analysis.beats, timeMs);
  const currentSection = getCurrentSection(liveSections, timeMs);
  const kindColor = currentSection ? (KIND_COLORS[currentSection.kind] ?? '#6a6a78') : '#6a6a78';

  return (
    <div className={styles.root}>
      <Transport
        playing={playing}
        timeMs={timeMs}
        durationMs={song.duration_ms}
        onPlay={play}
        onPause={pause}
        onPrevSection={handlePrevSection}
        onNextSection={handleNextSection}
      />

      <div className={styles.body}>
        {/* Main content column */}
        <div className={styles.mainCol}>
          <div className={styles.zoomBar}>
            <span className={styles.zoomLabel}>ZOOM</span>
            <button className={styles.zoomBtn} onClick={zoomOut} disabled={zoomLevel === 1}>−</button>
            <span className={styles.zoomLevel}>{zoomLevel}×</span>
            <button className={styles.zoomBtn} onClick={zoomIn} disabled={zoomLevel === ZOOM_LEVELS[ZOOM_LEVELS.length - 1]}>+</button>
            {zoomLevel > 1 && (
              <button className={styles.zoomResetBtn} onClick={() => { setZoomLevel(1); setViewStartMs(0); }}>
                fit
              </button>
            )}
          </div>
          <div
            ref={waveformAreaRef}
            className={`${styles.waveformArea} ${styles.trackAligned}`}
            onWheel={handleWheel}
          >
            <div className={styles.trackAlignedLabel}>WAVEFORM</div>
            <Waveform
              peaks={windowPeaks ?? analysis.peaks}
              peaksArePrescaled={windowPeaks !== null}
              playheadMs={timeMs}
              durationMs={durationMs}
              viewStartMs={zoomLevel > 1 ? viewStartMs : undefined}
              viewEndMs={zoomLevel > 1 ? viewEndMs : undefined}
              sections={liveSections}
              accent="#4ade80"
              onSeek={seekMs}
            />
            <Ruler
              durationMs={durationMs}
              playheadMs={timeMs}
              onSeek={seekMs}
              viewStartMs={zoomLevel > 1 ? viewStartMs : undefined}
              viewEndMs={zoomLevel > 1 ? viewEndMs : undefined}
            />
          </div>

          <div className={styles.sectionsToolbar}>
            <span className={styles.sectionsLabel}>SECTIONS · {liveSections.length}</span>
            {editMode ? (
              <span className={styles.editHint}>
                drag boundaries · right-click for split / merge / delete · click dot to change kind
              </span>
            ) : (
              <span className={styles.editHint}>click edit to adjust boundaries</span>
            )}
            <button
              className={`${styles.sectionsEditBtn} ${editMode ? styles.sectionsEditBtnActive : ''}`}
              onClick={() => setEditMode(!editMode)}
            >
              {editMode ? '✓ Done' : '✎ Edit sections'}
            </button>
          </div>
          <div className={styles.trackAligned}>
            <div className={styles.trackAlignedLabel}>SECTIONS</div>
            <SectionStrip
              sections={liveSections}
              assignments={assignments}
              durationMs={durationMs}
              viewStartMs={zoomLevel > 1 ? viewStartMs : undefined}
              viewEndMs={zoomLevel > 1 ? viewEndMs : undefined}
              selectedIndex={selectedIndex}
              onSelect={(idx) => {
                setSelectedIndex(idx);
                seekMs(liveSections[idx]?.start_ms ?? 0);
              }}
              timeMs={timeMs}
              songId={song.song_id}
              detectedSections={analysis.detected_sections}
            />
          </div>

          <div className={styles.trackAligned}>
            <div className={styles.trackAlignedLabel}>LYRICS</div>
            <LyricTrack
              lines={analysis.lyrics ?? []}
              durationMs={durationMs}
              viewStartMs={zoomLevel > 1 ? viewStartMs : undefined}
              viewEndMs={zoomLevel > 1 ? viewEndMs : undefined}
            />
          </div>

          <div className={styles.previewRow}>
            <LightsPreview
              n={16}
              label={liveSections[selectedIndex]?.label ?? ''}
              energyPulse={0.5}
              accent={currentAssignment?.theme_id ? '#4ade80' : '#555'}
            />
          </div>

          <StemWaveforms
            songId={song.song_id}
            durationMs={durationMs}
            playheadMs={timeMs}
            viewStartMs={zoomLevel > 1 ? viewStartMs : undefined}
            viewEndMs={zoomLevel > 1 ? viewEndMs : undefined}
            onSeek={seekMs}
          />

          <div className={styles.tracksDrawer}>
            <div
              className={styles.drawerHeader}
              onClick={() => setDrawerOpen((o) => !o)}
            >
              <span className={styles.drawerTitle}>
                {drawerOpen ? '▾' : '▸'} RAW ALGORITHM TRACKS
              </span>
              <span className={styles.drawerCount}>
                {drawerDetectors.length - hiddenDetectors.size} / {drawerDetectors.length} visible
              </span>
              <div className={styles.drawerSpacer} />
              <span className={styles.drawerHint}>click to toggle · events flash near playhead</span>
            </div>

            {drawerOpen && (
              <div className={styles.drawerRows}>
                {drawerDetectors.map((det, i) => {
                  const isCurve = det.kind === 'curve';
                  const curveData = isCurve ? analysis.value_curves?.[det.name] : undefined;
                  const events = isCurve ? [] : getDetectorEvents(det.name, analysis, song.duration_ms, det.marks ?? 0);
                  return (
                    <AlgoTrack
                      key={det.name}
                      name={det.name}
                      library={det.library}
                      events={events}
                      markCount={det.marks ?? 0}
                      durationMs={song.duration_ms}
                      timeMs={timeMs}
                      visible={!hiddenDetectors.has(det.name)}
                      onToggle={() => toggleDetector(det.name)}
                      color={getLibraryColor(det.library)}
                      rowIdx={i}
                      viewStartMs={zoomLevel > 1 ? viewStartMs : undefined}
                      viewEndMs={zoomLevel > 1 ? viewEndMs : undefined}
                      onSeek={seekMs}
                      curve={curveData}
                    />
                  );
                })}
              </div>
            )}
          </div>

          {onNavigateTheme && (
            <button className={styles.themeBtn} onClick={onNavigateTheme}>
              Go to Theme →
            </button>
          )}
        </div>

        {/* Right inspector panel — collapsible */}
        {inspectorCollapsed && (
          <div
            className={styles.inspectorCollapsed}
            onClick={toggleInspector}
            title="Expand inspector"
          >
            <span className={styles.inspectorCollapsedLabel}>◂ INSPECTOR</span>
          </div>
        )}
        {!inspectorCollapsed && (
        <div className={styles.inspector}>
          <button
            className={styles.inspectorCollapseBtn}
            onClick={toggleInspector}
            title="Collapse inspector"
          >
            ▸
          </button>
          {editMode ? (
            /* Edit mode inspector — section list */
            <div className={styles.inspectorEditMode}>
              <div className={styles.inspectorEditHeader}>
                <span className={styles.inspectorEditTitle}>✎ EDITING SECTIONS</span>
                <button
                  className={styles.inspectorEditDone}
                  onClick={() => setEditMode(false)}
                >
                  Done · esc
                </button>
              </div>

              <div className={styles.inspectorEditHint}>
                drag edges to nudge · right-click for split / merge / delete
              </div>

              <div className={styles.inspectorEditActions}>
                <button
                  className={styles.inspectorActionBtn}
                  onClick={() => {
                    setSections(
                      analysis.detected_sections.map((s) => ({
                        ...s,
                        kind: s.kind as 'intro' | 'verse' | 'chorus' | 'solo' | 'bridge' | 'outro' | 'unknown',
                      }))
                    );
                  }}
                >
                  ↺ Reset to detected
                </button>
              </div>

              <div className={styles.inspectorSectionHeader}>
                SECTIONS · {liveSections.length}
              </div>

              <div className={styles.inspectorSectionList}>
                {liveSections.map((sec, i) => {
                  const isActive = timeMs >= sec.start_ms && timeMs < sec.end_ms;
                  const isSelected = selectedIndex === sec.index;
                  const durMs = sec.end_ms - sec.start_ms;
                  const color = KIND_COLORS[sec.kind] ?? '#6a6a78';
                  return (
                    <button
                      key={sec.index}
                      className={`${styles.sectionRow} ${isSelected ? styles.sectionRowSelected : ''} ${isActive ? styles.sectionRowActive : ''}`}
                      onClick={() => {
                        setSelectedIndex(i);
                        seekMs(sec.start_ms);
                      }}
                    >
                      <span
                        className={styles.sectionRowSwatch}
                        style={{ background: color }}
                      />
                      <span className={styles.sectionRowNum}>
                        {String(i + 1).padStart(2, '0')}
                      </span>
                      <span className={styles.sectionRowLabel}>{sec.label}</span>
                      <span className={styles.sectionRowKind}>{sec.kind}</span>
                      <span className={styles.sectionRowTime}>
                        {fmtMs(sec.start_ms)}–{fmtMs(sec.end_ms)}
                      </span>
                      <span className={styles.sectionRowDur}>
                        {fmtDuration(durMs)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            /* Normal inspector */
            <>
              {/* PLAYHEAD section */}
              <div className={styles.inspectorBlock}>
                <div className={styles.inspectorLabel}>PLAYHEAD</div>
                <div className={styles.timecode}>{fmtMs(timeMs)}</div>
                <div className={styles.barBeat}>
                  bar {currentBeat?.bar ?? 0} · beat {(currentBeat?.beat ?? 0) + 1} of 4
                </div>
              </div>

              {/* CURRENT SECTION section */}
              <div className={styles.inspectorBlock}>
                <div className={styles.inspectorLabel}>CURRENT SECTION</div>
                {currentSection ? (
                  <div className={styles.sectionInfo}>
                    <span
                      className={styles.sectionSwatch}
                      style={{ background: kindColor }}
                    />
                    <div className={styles.sectionInfoText}>
                      <div className={styles.sectionInfoLabel}>{currentSection.label}</div>
                      <div className={styles.sectionInfoKind}>{currentSection.kind}</div>
                    </div>
                  </div>
                ) : (
                  <div className={styles.sectionInfoKind}>—</div>
                )}
              </div>

              {/* SECTION TIMING section */}
              {currentSection && (
                <div className={styles.inspectorBlock}>
                  <div className={styles.inspectorLabel}>SECTION TIMING</div>
                  <div className={styles.timingRow}>
                    <span className={styles.timingKey}>Start</span>
                    <span className={styles.timingVal}>{fmtMs(currentSection.start_ms)}</span>
                  </div>
                  <div className={styles.timingRow}>
                    <span className={styles.timingKey}>End</span>
                    <span className={styles.timingVal}>{fmtMs(currentSection.end_ms)}</span>
                  </div>
                  <div className={styles.timingRow}>
                    <span className={styles.timingKey}>Duration</span>
                    <span className={styles.timingVal}>
                      {fmtDuration(currentSection.end_ms - currentSection.start_ms)}
                    </span>
                  </div>
                </div>
              )}

              <div className={styles.inspectorSpacer} />

              {/* Nudge buttons */}
              <div className={styles.inspectorNudge}>
                <button
                  className={styles.nudgeBtn}
                  onClick={() => seekMs(timeMs - 10)}
                >
                  nudge −10ms
                </button>
                <button
                  className={styles.nudgeBtn}
                  onClick={() => seekMs(timeMs + 10)}
                >
                  nudge +10ms
                </button>
              </div>
            </>
          )}

          {/* Edit mode toggle — always at bottom */}
          <div className={styles.inspectorEditToggle}>
            <button
              className={`${styles.editToggleBtn} ${editMode ? styles.editToggleBtnActive : ''}`}
              onClick={() => setEditMode(!editMode)}
            >
              {editMode ? '✓ Done editing' : '✎ Edit sections'}
            </button>
          </div>
        </div>
        )}
      </div>
    </div>
  );
}
