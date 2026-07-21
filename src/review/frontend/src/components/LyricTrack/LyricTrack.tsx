import React from 'react';
import styles from './LyricTrack.module.css';

interface LyricLine {
  t_ms: number;
  duration_ms: number;
  text: string;
}

interface LyricTrackProps {
  lines: LyricLine[];
  /** True when some lyric text was available (fed chorus/section
   * detection) even though it produced no timed lines here -- covers
   * BOTH a user-pasted fallback and an untimed plain-text provider result
   * (a documented existing case, not just paste) -- distinguishes either
   * from "nothing was found at all" (user-reported confusion, 2026-07-21:
   * both cases otherwise showed the same "No synced lyrics found"
   * message). Deliberately doesn't say "pasted" specifically -- that
   * can't be verified from this flag alone. */
  textFound?: boolean;
  durationMs: number;
  viewStartMs?: number;
  viewEndMs?: number;
}

export function LyricTrack({ lines, textFound, durationMs, viewStartMs, viewEndMs }: LyricTrackProps) {
  const viewStart = viewStartMs ?? 0;
  const viewEnd = viewEndMs ?? durationMs;
  const windowMs = viewEnd - viewStart || durationMs;

  if (lines.length === 0) {
    return (
      <div className={styles.strip} data-testid="lyric-track-empty">
        <span className={styles.emptyLabel}>
          {textFound ? 'Lyrics found (no timing)' : 'No synced lyrics found'}
        </span>
      </div>
    );
  }

  return (
    <div className={styles.strip} data-testid="lyric-track">
      {lines.map((line, i) => {
        const start = line.t_ms;
        const end = line.t_ms + line.duration_ms;
        const clampedStart = Math.max(start, viewStart);
        const clampedEnd = Math.min(end, viewEnd);
        if (clampedEnd <= clampedStart) return null;

        const leftPct = ((clampedStart - viewStart) / windowMs) * 100;
        const widthPct = ((clampedEnd - clampedStart) / windowMs) * 100;

        return (
          <span
            key={i}
            data-testid="lyric-line"
            className={styles.line}
            style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
            title={line.text}
          >
            {line.text}
          </span>
        );
      })}
    </div>
  );
}
