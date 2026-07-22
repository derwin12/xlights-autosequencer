import React, { useMemo, useState } from 'react';
import styles from './SingerLane.module.css';

export interface AttrWord {
  label: string;
  start_ms: number;
  end_ms: number;
  singers: string[];
  backing: boolean;
}

interface SingerLaneProps {
  words: AttrWord[];
  durationMs: number;
  viewStartMs?: number;
  viewEndMs?: number;
  /** Called with the full edited word array after a relabel; parent persists it. */
  onCommit: (words: AttrWord[]) => void;
}

const PALETTE = [
  '#4ade80', '#60a5fa', '#f472b6', '#fbbf24', '#a78bfa', '#f87171', '#34d399',
];
const BACKING_COLOR = '#6b7280';

/** Distinct singer names in first-appearance order (backing excluded). */
export function distinctSingers(words: AttrWord[]): string[] {
  const seen: string[] = [];
  for (const w of words) {
    for (const name of w.singers ?? []) {
      if (!seen.includes(name)) seen.push(name);
    }
  }
  return seen;
}

function chipBackground(w: AttrWord, colorOf: (name: string) => string): string {
  if (w.backing || w.singers.length === 0) return BACKING_COLOR;
  if (w.singers.length === 1) return colorOf(w.singers[0]);
  // Shared / "Both": stripe the singers' colors so it reads as multi.
  const stops = w.singers.map((n, i) => {
    const c = colorOf(n);
    const a = (i / w.singers.length) * 100;
    const b = ((i + 1) / w.singers.length) * 100;
    return `${c} ${a}%, ${c} ${b}%`;
  });
  return `linear-gradient(90deg, ${stops.join(', ')})`;
}

export function SingerLane({ words, durationMs, viewStartMs, viewEndMs, onCommit }: SingerLaneProps) {
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const singers = useMemo(() => distinctSingers(words), [words]);
  const colorOf = useMemo(() => {
    const map = new Map<string, string>();
    singers.forEach((n, i) => map.set(n, PALETTE[i % PALETTE.length]));
    return (name: string) => map.get(name) ?? BACKING_COLOR;
  }, [singers]);

  const viewStart = viewStartMs ?? 0;
  const viewEnd = viewEndMs ?? durationMs;
  const windowMs = viewEnd - viewStart || durationMs;

  function toggle(i: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i); else next.add(i);
      return next;
    });
  }

  function applyToSelection(target: 'backing' | 'both' | { singer: string }) {
    if (selected.size === 0) return;
    const next = words.map((w, i) => {
      if (!selected.has(i)) return w;
      if (target === 'backing') return { ...w, singers: [], backing: true };
      if (target === 'both') return { ...w, singers: [...singers], backing: false };
      return { ...w, singers: [target.singer], backing: false };
    });
    onCommit(next);
    setSelected(new Set());
  }

  if (words.length === 0) {
    return (
      <div className={styles.lane} data-testid="singer-lane-empty">
        <span className={styles.emptyLabel}>No attributed lyrics</span>
      </div>
    );
  }

  return (
    <div className={styles.wrap} data-testid="singer-lane">
      <div className={styles.lane}>
        {words.map((w, i) => {
          const s = Math.max(w.start_ms, viewStart);
          const e = Math.min(w.end_ms, viewEnd);
          if (e <= s) return null;
          const left = ((s - viewStart) / windowMs) * 100;
          const width = Math.max(((e - s) / windowMs) * 100, 0.4);
          return (
            <button
              key={i}
              type="button"
              data-testid="singer-word"
              data-idx={i}
              data-singers={(w.backing ? ['Backing'] : w.singers).join('|')}
              data-selected={selected.has(i) ? 'true' : 'false'}
              className={styles.chip}
              style={{ left: `${left}%`, width: `${width}%`, background: chipBackground(w, colorOf) }}
              title={`${w.label} — ${w.backing ? 'Backing' : w.singers.join(' & ') || 'unassigned'}`}
              onClick={() => toggle(i)}
            >
              <span className={styles.chipLabel}>{w.label}</span>
            </button>
          );
        })}
      </div>
      {selected.size > 0 && (
        <div className={styles.toolbar} data-testid="singer-toolbar">
          <span className={styles.count}>{selected.size} selected →</span>
          {singers.map((name) => (
            <button key={name} type="button" data-testid={`relabel-${name}`}
                    className={styles.action} style={{ borderColor: colorOf(name) }}
                    onClick={() => applyToSelection({ singer: name })}>
              {name}
            </button>
          ))}
          {singers.length > 1 && (
            <button type="button" data-testid="relabel-both" className={styles.action}
                    onClick={() => applyToSelection('both')}>Both</button>
          )}
          <button type="button" data-testid="relabel-backing" className={styles.action}
                  onClick={() => applyToSelection('backing')}>Backing</button>
          <button type="button" data-testid="relabel-clear" className={styles.action}
                  onClick={() => setSelected(new Set())}>Clear</button>
        </div>
      )}
    </div>
  );
}
