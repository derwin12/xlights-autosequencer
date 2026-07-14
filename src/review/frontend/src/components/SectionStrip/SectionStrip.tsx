import React, { useEffect, useRef, useState } from 'react';
import styles from './SectionStrip.module.css';
import { useSectionsStore, Section } from '../../store/sections';

// Broader shape accepted from callers (kind is string, not narrow union)
interface RawSection {
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

interface ThemeSummary {
  theme_id: string;
  accent: string;
}

interface SectionStripProps {
  sections: RawSection[];
  assignments: Assignment[];
  themes?: ThemeSummary[];
  durationMs: number;
  viewStartMs?: number;
  viewEndMs?: number;
  selectedIndex?: number;
  onSelect?: (index: number) => void;
  timeMs?: number;
  songId?: string;
  detectedSections?: RawSection[];
}

// Fallback accent for legacy assignment ids that predate the theme catalog's
// `accent` field (kept so old saved sessions still render a color instead of
// falling through to the '#555' default).
const LEGACY_THEME_ACCENTS: Record<string, string> = {
  'shimmer-wash': '#4ade80',
  'driving-pulse': '#d97757',
  'peak-flash': '#facc15',
  'solo-chase': '#38bdf8',
  'bridge-burn': '#f97316',
  'neutral-glow': '#e2e8f0',
};

const KIND_CYCLE: Array<Section['kind']> = [
  'intro', 'verse', 'pre_chorus', 'chorus', 'bridge', 'solo', 'outro', 'unknown',
];

interface ContextMenu {
  x: number;
  y: number;
  sectionIdx: number;
}

function formatMs(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** Coerce a RawSection to the store's narrow Section type */
function coerce(s: RawSection): Section {
  return s as Section;
}

function coerceAll(arr: RawSection[]): Section[] {
  return arr as Section[];
}

function persistSections(songId: string | undefined, sections: RawSection[]) {
  if (!songId) return;
  fetch(`/api/v1/songs/${songId}/sections`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sections }),
  }).catch(() => {
    // fire-and-forget
  });
}

export function SectionStrip({
  sections: propSections,
  assignments,
  themes,
  durationMs,
  viewStartMs,
  viewEndMs,
  selectedIndex: propSelectedIndex,
  onSelect,
  timeMs = 0,
  songId,
  detectedSections,
}: SectionStripProps) {
  const themeAccentById = Object.fromEntries(
    (themes ?? []).map((t) => [t.theme_id, t.accent])
  );
  const {
    sections: storeSections,
    editMode,
    selectedIndex: storeSelectedIndex,
    setSections,
    setSelectedIndex,
  } = useSectionsStore();

  // Seed the store on mount if empty
  useEffect(() => {
    if (propSections.length > 0 && storeSections.length === 0) {
      setSections(coerceAll(propSections));
    }
  }, [propSections, storeSections.length, setSections]);

  // Use store sections in edit mode; prop sections otherwise
  const sections: RawSection[] =
    editMode && storeSections.length > 0 ? storeSections : propSections;
  const selectedIndex = editMode
    ? (storeSelectedIndex ?? propSelectedIndex ?? 0)
    : (propSelectedIndex ?? 0);

  const assignmentByIndex = Object.fromEntries(
    assignments.map((a) => [a.section_index, a])
  );

  const stripRef = useRef<HTMLDivElement>(null);
  const [menu, setMenu] = useState<ContextMenu | null>(null);
  const [drag, setDrag] = useState<{ sectionIdx: number } | null>(null);

  // Close context menu on outside click or Escape
  useEffect(() => {
    if (!menu) return;
    const handleClick = () => setMenu(null);
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenu(null);
    };
    window.addEventListener('click', handleClick);
    window.addEventListener('keydown', handleKey);
    return () => {
      window.removeEventListener('click', handleClick);
      window.removeEventListener('keydown', handleKey);
    };
  }, [menu]);

  // Drag boundary logic
  useEffect(() => {
    if (!drag || !stripRef.current) return;
    const handleMove = (e: MouseEvent) => {
      const rect = stripRef.current!.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      const vStart = viewStartMs ?? 0;
      const vEnd = viewEndMs ?? durationMs;
      const newMs = Math.round(vStart + pct * (vEnd - vStart));

      const updated = sections.map((s) => ({ ...s }));
      const cur = updated[drag.sectionIdx];
      const next = updated[drag.sectionIdx + 1] ?? null;

      const minMs = cur.start_ms + 500;
      const maxMs = next ? next.end_ms - 500 : durationMs;
      const clampedMs = Math.max(minMs, Math.min(maxMs, newMs));

      cur.end_ms = clampedMs;
      if (next) next.start_ms = clampedMs;

      setSections(coerceAll(updated));
    };
    const handleUp = () => {
      setDrag(null);
      persistSections(songId, sections);
    };
    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleUp);
    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleUp);
    };
  }, [drag, sections, durationMs, viewStartMs, viewEndMs, setSections, songId]);

  function cycleKind(idx: number) {
    const sec = sections[idx];
    const kindIdx = KIND_CYCLE.indexOf(sec.kind as Section['kind']);
    const nextKind = KIND_CYCLE[(kindIdx + 1) % KIND_CYCLE.length];
    const updated = sections.map((s, i) =>
      i === idx ? { ...s, kind: nextKind as string } : { ...s }
    );
    setSections(coerceAll(updated));
    persistSections(songId, updated);
  }

  function splitAtPlayhead(sectionIdx: number) {
    const sec = sections[sectionIdx];
    if (timeMs <= sec.start_ms + 500 || timeMs >= sec.end_ms - 500) return;

    const first: RawSection = { ...sec, end_ms: timeMs };
    const second: RawSection = { ...sec, start_ms: timeMs, label: sec.label + ' (2)' };
    const updated = [
      ...sections.slice(0, sectionIdx),
      first,
      second,
      ...sections.slice(sectionIdx + 1),
    ].map((s, i) => ({ ...s, index: i }));

    setSections(coerceAll(updated));
    persistSections(songId, updated);
  }

  function mergeWithNext(sectionIdx: number) {
    if (sectionIdx >= sections.length - 1) return;
    const cur = sections[sectionIdx];
    const next = sections[sectionIdx + 1];
    const merged: RawSection = { ...cur, end_ms: next.end_ms };
    const updated = [
      ...sections.slice(0, sectionIdx),
      merged,
      ...sections.slice(sectionIdx + 2),
    ].map((s, i) => ({ ...s, index: i }));

    setSections(coerceAll(updated));
    persistSections(songId, updated);
  }

  function deleteSection(sectionIdx: number) {
    if (sections.length <= 1) return;
    const updated = [
      ...sections.slice(0, sectionIdx),
      ...sections.slice(sectionIdx + 1),
    ].map((s, i) => ({ ...s, index: i }));

    setSections(coerceAll(updated));
    persistSections(songId, updated);
  }

  function resetToDetected() {
    const base = detectedSections ?? propSections;
    setSections(coerceAll(base));
    persistSections(songId, base);
  }

  function handleChipClick(i: number) {
    if (editMode) setSelectedIndex(i);
    onSelect?.(sections[i].index);
  }

  const viewStart = viewStartMs ?? 0;
  const viewEnd = viewEndMs ?? durationMs;
  const windowMs = viewEnd - viewStart || durationMs;

  // ms → % within the visible window
  function msToWindowPct(ms: number): number {
    return ((ms - viewStart) / windowMs) * 100;
  }

  return (
    <div
      ref={stripRef}
      className={`${styles.strip} ${editMode ? styles.stripEdit : ''}`}
    >
      {sections.map((sec, i) => {
        // Clip section to visible window
        const clampedStart = Math.max(sec.start_ms, viewStart);
        const clampedEnd = Math.min(sec.end_ms, viewEnd);
        if (clampedEnd <= clampedStart) return null;

        const leftPct = msToWindowPct(clampedStart);
        const widthPct = ((clampedEnd - clampedStart) / windowMs) * 100;
        const assignment = assignmentByIndex[sec.index];
        const accent = assignment?.theme_id
          ? (themeAccentById[assignment.theme_id]
              ?? LEGACY_THEME_ACCENTS[assignment.theme_id]
              ?? '#555')
          : '#555';
        const isSelected = selectedIndex === sec.index;

        return (
          <button
            key={sec.index}
            data-testid="section-chip"
            data-selected={isSelected ? 'true' : 'false'}
            className={`${styles.chip} ${isSelected ? styles.selected : ''} ${editMode ? styles.chipEdit : ''}`}
            style={{ position: 'absolute', left: `${leftPct}%`, width: `${widthPct}%`, borderColor: accent }}
            onClick={() => handleChipClick(i)}
            onContextMenu={
              editMode
                ? (e) => {
                    e.preventDefault();
                    setMenu({ x: e.clientX, y: e.clientY, sectionIdx: i });
                  }
                : undefined
            }
            title={sec.label}
          >
            {editMode && (
              <span
                className={styles.kindDot}
                style={{ background: accent }}
                onClick={(e) => {
                  e.stopPropagation();
                  cycleKind(i);
                }}
                title={`${sec.kind} · click to cycle`}
              />
            )}
            <span className={styles.chipLabel}>{sec.label}</span>
            {editMode && (
              <span className={styles.chipKindAbbr}>{sec.kind.slice(0, 3)}</span>
            )}
          </button>
        );
      })}

      {/* Draggable boundary handles in edit mode */}
      {editMode &&
        sections.slice(0, -1).map((sec, i) => {
          const boundaryMs = sec.end_ms;
          if (boundaryMs <= viewStart || boundaryMs >= viewEnd) return null;
          const leftPct = msToWindowPct(boundaryMs);
          const isDragging = drag?.sectionIdx === i;
          return (
            <div
              key={`handle-${i}`}
              className={`${styles.boundaryHandle} ${isDragging ? styles.boundaryHandleDragging : ''}`}
              style={{ left: `${leftPct}%` }}
              onMouseDown={(e) => {
                e.stopPropagation();
                setDrag({ sectionIdx: i });
              }}
              title={`boundary · ${formatMs(sec.end_ms)}`}
            >
              <div
                className={`${styles.boundaryLine} ${isDragging ? styles.boundaryLineDragging : ''}`}
              />
              <div
                className={`${styles.boundaryGrip} ${isDragging ? styles.boundaryGripDragging : ''}`}
              />
            </div>
          );
        })}

      {/* Context menu */}
      {menu && (
        <div
          className={styles.contextMenu}
          style={{ left: menu.x, top: menu.y }}
          onClick={(e) => e.stopPropagation()}
          onContextMenu={(e) => e.preventDefault()}
        >
          <button
            className={styles.menuItem}
            onClick={() => {
              splitAtPlayhead(menu.sectionIdx);
              setMenu(null);
            }}
            disabled={
              timeMs <= (sections[menu.sectionIdx]?.start_ms ?? 0) + 500 ||
              timeMs >= (sections[menu.sectionIdx]?.end_ms ?? 0) - 500
            }
          >
            ✂ Split at playhead
          </button>
          <button
            className={styles.menuItem}
            onClick={() => {
              mergeWithNext(menu.sectionIdx);
              setMenu(null);
            }}
            disabled={menu.sectionIdx >= sections.length - 1}
          >
            Merge with next →
          </button>
          <button
            className={styles.menuItem}
            onClick={() => {
              deleteSection(menu.sectionIdx);
              setMenu(null);
            }}
            disabled={sections.length <= 1}
          >
            Delete
          </button>
          <div className={styles.menuSep} />
          <button
            className={styles.menuItem}
            onClick={() => {
              resetToDetected();
              setMenu(null);
            }}
          >
            ↺ Reset to detected
          </button>
        </div>
      )}
    </div>
  );
}

// Suppress unused import warning — coerce is used inline above
void coerce;
