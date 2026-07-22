import React, { useState } from 'react';
import styles from './PasteLyricsDialog.module.css';

export interface LyricsCheckResult {
  found: boolean;
  reason: string | null;
  line_count: number;
  preview: string[];
  song_duration_ms?: number | null;
  lyrics_duration_ms?: number | null;
  source?: 'pasted';
}

interface PasteLyricsDialogProps {
  title: string;
  artist: string;
  /** Called with the server response after a successful paste. */
  onSaved: (result: LyricsCheckResult) => void;
  onCancel: () => void;
}

/**
 * Fallback for songs no syncedlyrics provider has indexed (e.g. a brand-new
 * release) — the user finds lyrics themselves and pastes them in here. Text
 * is validated/previewed by the same backend path a provider result goes
 * through, so it lands in `lyricsCheckResult` identically to "Check Lyrics".
 */
export function PasteLyricsDialog({ title, artist, onSaved, onCancel }: PasteLyricsDialogProps) {
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    const trimmed = text.trim();
    if (!trimmed) {
      setError('Paste some lyrics text first');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/v1/lyrics/paste', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, artist, lyrics_text: trimmed }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error?.message || 'Saving pasted lyrics failed');
      onSaved(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Saving pasted lyrics failed');
      setSaving(false);
    }
  }

  return (
    <div className={styles.overlay}>
      <div role="dialog" aria-modal="true" aria-label="Paste lyrics" className={styles.dialog}>
        <h2 className={styles.title}>Paste Lyrics</h2>
        <p className={styles.subtitle}>
          No provider found lyrics for this song automatically. Find the lyrics
          yourself (e.g. a lyrics site) and paste the full text below.
        </p>

        <textarea
          className={styles.textarea}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste lyrics here…"
          aria-label="Lyrics text"
          autoFocus
        />

        {error && <p role="alert" className={styles.error}>{error}</p>}

        <div className={styles.actions}>
          <button className={styles.btnCancel} data-testid="paste-lyrics-cancel" onClick={onCancel} disabled={saving}>
            Cancel
          </button>
          <button className={styles.btnConfirm} data-testid="paste-lyrics-save" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save Lyrics'}
          </button>
        </div>
      </div>
    </div>
  );
}
