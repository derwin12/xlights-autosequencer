import { useEffect, useState } from 'react';
import styles from './Pictures.module.css';

interface ImageSuggestion {
  word: string;
  start_ms: number;
  end_ms: number;
  matched_file: string;
  matched_tag: string;
  score: number;
}

interface ImageTopic {
  word: string;
  start_ms: number;
  end_ms: number;
}

interface Song {
  song_id: string;
  title: string;
}

interface VocalWord {
  label?: string;
  word?: string;
  start_ms: number;
  end_ms: number;
}

interface PicturesScreenProps {
  song: Song;
  imageSuggestions: ImageSuggestion[];
  imageTopics: ImageTopic[];
  vocalWords?: VocalWord[];
  onContinue: () => void;
}

type MotionType = 'shake' | 'bounce' | 'spin' | 'flash';
const MOTIONS: MotionType[] = ['shake', 'bounce', 'spin', 'flash'];

// Candidate words for the "add from lyrics" picker -- distinct real words,
// no noun-only bias (unlike Pictures' find_unmatched_topics, action words
// like "explode"/"jump" are exactly what a Moving Head trigger wants).
const MH_STOPWORDS = new Set([
  'the', 'and', 'a', 'an', 'to', 'of', 'in', 'on', 'is', 'it', 'you', 'i',
  'me', 'my', 'we', 'us', 'our', 'that', 'this', 'for', 'with', 'your',
  'all', 'these', 'its', 'nobody', 'what', 'where', 'how', 'from', 'until',
  'will', 'just', 'maybe',
]);

function lyricWordCandidates(words: VocalWord[]): { word: string; start_ms: number }[] {
  const seen = new Map<string, number>();
  for (const w of words) {
    const raw = (w.label || w.word || '').toLowerCase().replace(/[^a-z]/g, '');
    if (raw.length < 3 || MH_STOPWORDS.has(raw) || seen.has(raw)) continue;
    seen.set(raw, w.start_ms);
  }
  return Array.from(seen.entries()).map(([word, start_ms]) => ({ word, start_ms }));
}

// Unmap/Shadow act on ONE lyric occurrence, not every occurrence of a
// word — ignored/shadowWords are keyed by (word, start_ms), not word alone.
function occKey(word: string, startMs: number): string {
  return `${word.toLowerCase()}|${startMs}`;
}

function occKeysFromOccurrences(occurrences: { word: string; start_ms: number }[]): Set<string> {
  return new Set(occurrences.map((o) => occKey(o.word, o.start_ms)));
}

function formatTimestamp(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function buildImagePrompt(word: string): string {
  return `Subject: ${word.toLowerCase()}.
Style: Minimalist 2D flat 8-bit pixel art illustration. Non-anthropomorphic (no faces or eyes), clean edges, simple cel-shading, limited vibrant color palette, no gradients. Perfectly horizontal and vertical pixel lines.
Outlines: Soft, colored outlines that match the object's palette (no black outlines).
Background: Placed on a solid, pure black background (#000000). Completely isolated with no white sticker borders, no outer glow, no drop shadows, and no borders.`;
}

// Gemini doesn't accept a prompt in the URL either, so the popup keeps the
// copy/paste flow: copy the prompt, then paste it on the Gemini page.
const GEMINI_CREATE_URL = 'https://gemini.google.com/app';

async function openExternal(url: string) {
  try {
    const { open } = await import('@tauri-apps/plugin-shell');
    await open(url);
  } catch {
    window.open(url, '_blank');
  }
}

export function Pictures({ song, imageSuggestions, imageTopics, vocalWords, onContinue }: PicturesScreenProps) {
  const [uploaded, setUploaded] = useState<Set<string>>(new Set());
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [promptWord, setPromptWord] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [ignored, setIgnored] = useState<Set<string>>(new Set());
  const [shadowWords, setShadowWords] = useState<Set<string>>(new Set());
  const [keywordMotions, setKeywordMotions] = useState<Record<string, string>>({});
  const [candidateMotions, setCandidateMotions] = useState<Record<string, MotionType>>({});
  const [newWord, setNewWord] = useState('');
  const [newMotion, setNewMotion] = useState<MotionType>('shake');

  useEffect(() => {
    fetch(`/api/v1/songs/${song.song_id}/ignored-images`)
      .then((r) => (r.ok ? r.json() : { occurrences: [] }))
      .then((body) => setIgnored(occKeysFromOccurrences(body.occurrences ?? [])))
      .catch(() => {});
  }, [song.song_id]);

  useEffect(() => {
    fetch(`/api/v1/songs/${song.song_id}/moving-head-keywords`)
      .then((r) => (r.ok ? r.json() : { keywords: {} }))
      .then((body) => setKeywordMotions(body.keywords ?? {}))
      .catch(() => {});
  }, [song.song_id]);

  useEffect(() => {
    fetch(`/api/v1/songs/${song.song_id}/shadow-words`)
      .then((r) => (r.ok ? r.json() : { occurrences: [] }))
      .then((body) => setShadowWords(occKeysFromOccurrences(body.occurrences ?? [])))
      .catch(() => {});
  }, [song.song_id]);

  async function toggleShadowWord(word: string, startMs: number) {
    const token = word.toLowerCase();
    setError(null);
    const isShadow = shadowWords.has(occKey(token, startMs));
    try {
      const res = await fetch(
        `/api/v1/songs/${song.song_id}/shadow-words${
          isShadow ? `/${encodeURIComponent(token)}/${startMs}` : ''
        }`,
        isShadow
          ? { method: 'DELETE' }
          : {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ word: token, start_ms: startMs }),
            },
      );
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Failed to update shadow word');
        return;
      }
      setShadowWords(occKeysFromOccurrences(body.occurrences ?? []));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    }
  }

  async function addKeyword(word: string, motion: MotionType) {
    const token = word.trim().toLowerCase();
    if (!token) return;
    setError(null);
    try {
      const res = await fetch(`/api/v1/songs/${song.song_id}/moving-head-keywords`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word: token, motion }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Failed to add keyword');
        return;
      }
      setKeywordMotions(body.keywords ?? {});
      setNewWord('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    }
  }

  async function removeKeyword(word: string) {
    setError(null);
    try {
      const res = await fetch(
        `/api/v1/songs/${song.song_id}/moving-head-keywords/${encodeURIComponent(word)}`,
        { method: 'DELETE' },
      );
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Failed to remove keyword');
        return;
      }
      setKeywordMotions(body.keywords ?? {});
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    }
  }

  const lyricCandidates = lyricWordCandidates(vocalWords ?? [])
    .filter((c) => !(c.word in keywordMotions));

  async function ignoreMatch(word: string, startMs: number) {
    const token = word.toLowerCase();
    setError(null);
    try {
      const res = await fetch(`/api/v1/songs/${song.song_id}/ignored-images`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word: token, start_ms: startMs }),
      });
      if (!res.ok) {
        const body = await res.json();
        setError(body?.error?.message ?? 'Failed to unmap');
        return;
      }
      setIgnored((prev) => new Set(prev).add(occKey(token, startMs)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    }
  }

  async function restoreMatch(word: string, startMs: number) {
    const token = word.toLowerCase();
    setError(null);
    try {
      const res = await fetch(
        `/api/v1/songs/${song.song_id}/ignored-images/${encodeURIComponent(token)}/${startMs}`,
        { method: 'DELETE' },
      );
      if (!res.ok) {
        const body = await res.json();
        setError(body?.error?.message ?? 'Failed to restore');
        return;
      }
      setIgnored((prev) => {
        const next = new Set(prev);
        next.delete(occKey(token, startMs));
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    }
  }

  function openCreateImage(word: string) {
    setPromptWord(word);
    setCopied(false);
  }

  async function copyPrompt(prompt: string) {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
    } catch {
      setError('Could not copy to clipboard — select the text and copy manually.');
    }
  }

  async function handleUpload(topic: ImageTopic, file: File) {
    setUploading(topic.word);
    setError(null);
    try {
      const form = new FormData();
      form.append('image', file);
      form.append('tag', topic.word.toLowerCase());
      const res = await fetch('/api/v1/images', { method: 'POST', body: form });
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Upload failed');
        return;
      }
      setUploaded((prev) => new Set(prev).add(topic.word));
      // Re-uploading an image for an unmapped occurrence means the user
      // wants it matched again — lift the per-occurrence ignore automatically.
      if (ignored.has(occKey(topic.word, topic.start_ms))) restoreMatch(topic.word, topic.start_ms);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    } finally {
      setUploading(null);
    }
  }

  const remainingTopics = imageTopics.filter((t) => !uploaded.has(t.word));
  const activeSuggestions = imageSuggestions.filter(
    (s) => !ignored.has(occKey(s.word, s.start_ms)),
  );
  // Unmapped occurrences go back to "Suggested topics" — one row per
  // unmapped occurrence, not deduped by word (each occurrence is unmapped
  // independently now, so other occurrences of the same word may still be
  // mapped and appear in "Already matched").
  const ignoredTopics = imageSuggestions.filter(
    (s) => ignored.has(occKey(s.word, s.start_ms)) && !uploaded.has(s.word),
  );

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.title}>{song.title}</h2>
        <button className={styles.continueBtn} onClick={onContinue}>
          Continue to Export
        </button>
      </div>

      <p className={styles.intro}>
        Pictures effects cycle through your uploaded image library on Matrix and Mega Tree props.
        The library is shared across every song — an image you upload here for one song's lyrics
        is automatically suggested again for any future song that mentions the same word.
      </p>

      {error && <p className={styles.error}>{error}</p>}

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Suggested topics</h3>
        <p className={styles.sectionHint}>
          These lyric words don't have a matching image in your library yet. Upload one to make
          it available for this song (and any future song mentioning the same word).
        </p>
        {remainingTopics.length === 0 && ignoredTopics.length === 0 ? (
          <p className={styles.empty}>No unmatched topics — nothing to upload.</p>
        ) : (
          <ul className={styles.topicList}>
            {ignoredTopics.map((s) => (
              <li key={`ignored-${s.word}-${s.start_ms}`} className={styles.topicItem}>
                <span className={styles.topicTime}>{formatTimestamp(s.start_ms)}</span>
                <span className={styles.topicWord}>&ldquo;{s.word}&rdquo;</span>
                <span className={styles.unmappedNote}>unmapped from {s.matched_file}</span>
                <button
                  type="button"
                  className={styles.createImageBtn}
                  onClick={() => openCreateImage(s.word)}
                >
                  Create image
                </button>
                <button
                  type="button"
                  className={styles.createImageBtn}
                  aria-pressed={shadowWords.has(occKey(s.word, s.start_ms))}
                  onClick={() => toggleShadowWord(s.word, s.start_ms)}
                >
                  {shadowWords.has(occKey(s.word, s.start_ms)) ? 'Shadow ✓' : 'Shadow'}
                </button>
                <label className={styles.uploadLabel}>
                  {uploading === s.word ? 'Uploading…' : 'Choose image'}
                  <input
                    type="file"
                    accept=".gif,.png,.bmp,.jpg,.jpeg"
                    className={styles.uploadInput}
                    disabled={uploading === s.word}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleUpload(s, file);
                      e.target.value = '';
                    }}
                  />
                </label>
                <button
                  type="button"
                  className={styles.createImageBtn}
                  onClick={() => restoreMatch(s.word, s.start_ms)}
                >
                  Restore match
                </button>
              </li>
            ))}
            {remainingTopics.map((t) => (
              <li key={`${t.word}-${t.start_ms}`} className={styles.topicItem}>
                <span className={styles.topicTime}>{formatTimestamp(t.start_ms)}</span>
                <span className={styles.topicWord}>&ldquo;{t.word}&rdquo;</span>
                <button
                  type="button"
                  className={styles.createImageBtn}
                  onClick={() => openCreateImage(t.word)}
                >
                  Create image
                </button>
                <button
                  type="button"
                  className={styles.createImageBtn}
                  aria-pressed={shadowWords.has(occKey(t.word, t.start_ms))}
                  onClick={() => toggleShadowWord(t.word, t.start_ms)}
                >
                  {shadowWords.has(occKey(t.word, t.start_ms)) ? 'Shadow ✓' : 'Shadow'}
                </button>
                <label className={styles.uploadLabel}>
                  {uploading === t.word ? 'Uploading…' : 'Choose image'}
                  <input
                    type="file"
                    accept=".gif,.png,.bmp,.jpg,.jpeg"
                    className={styles.uploadInput}
                    disabled={uploading === t.word}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleUpload(t, file);
                      e.target.value = '';
                    }}
                  />
                </label>
              </li>
            ))}
          </ul>
        )}
      </section>

      {(activeSuggestions.length > 0 || uploaded.size > 0) && (
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>Already matched</h3>
          <ul className={styles.topicList}>
            {activeSuggestions.map((s, i) => (
              <li key={`matched-${s.word}-${s.start_ms}-${i}`} className={styles.topicItem}>
                <span className={styles.topicTime}>{formatTimestamp(s.start_ms)}</span>
                <span className={styles.topicWord}>&ldquo;{s.word}&rdquo;</span>
                <span className={styles.matchedArrow}>&rarr;</span>
                <span className={styles.matchedFile}>{s.matched_file}</span>
                <button
                  type="button"
                  className={styles.createImageBtn}
                  onClick={() => openCreateImage(s.word)}
                >
                  Create image
                </button>
                <button
                  type="button"
                  className={styles.createImageBtn}
                  aria-pressed={shadowWords.has(occKey(s.word, s.start_ms))}
                  onClick={() => toggleShadowWord(s.word, s.start_ms)}
                >
                  {shadowWords.has(occKey(s.word, s.start_ms)) ? 'Shadow ✓' : 'Shadow'}
                </button>
                <label className={styles.uploadLabel}>
                  {uploading === s.word ? 'Uploading…' : 'Choose image'}
                  <input
                    type="file"
                    accept=".gif,.png,.bmp,.jpg,.jpeg"
                    className={styles.uploadInput}
                    disabled={uploading === s.word}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleUpload(s, file);
                      e.target.value = '';
                    }}
                  />
                </label>
                <button
                  type="button"
                  className={styles.createImageBtn}
                  onClick={() => ignoreMatch(s.word, s.start_ms)}
                >
                  Unmap
                </button>
              </li>
            ))}
            {imageTopics.filter((t) => uploaded.has(t.word)).map((t) => (
              <li key={`uploaded-${t.word}-${t.start_ms}`} className={styles.topicItem}>
                <span className={styles.topicTime}>{formatTimestamp(t.start_ms)}</span>
                <span className={styles.topicWord}>&ldquo;{t.word}&rdquo;</span>
                <span className={styles.matchedArrow}>&rarr;</span>
                <span className={styles.matchedFile}>uploaded</span>
                <button
                  type="button"
                  className={styles.createImageBtn}
                  onClick={() => openCreateImage(t.word)}
                >
                  Create image
                </button>
                <button
                  type="button"
                  className={styles.createImageBtn}
                  aria-pressed={shadowWords.has(occKey(t.word, t.start_ms))}
                  onClick={() => toggleShadowWord(t.word, t.start_ms)}
                >
                  {shadowWords.has(occKey(t.word, t.start_ms)) ? 'Shadow ✓' : 'Shadow'}
                </button>
                <label className={styles.uploadLabel}>
                  {uploading === t.word ? 'Uploading…' : 'Choose image'}
                  <input
                    type="file"
                    accept=".gif,.png,.bmp,.jpg,.jpeg"
                    className={styles.uploadInput}
                    disabled={uploading === t.word}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleUpload(t, file);
                      e.target.value = '';
                    }}
                  />
                </label>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Moving Head Triggers</h3>
        <p className={styles.sectionHint}>
          These lyric words trigger a Moving Head accent when sung. Uncheck a built-in to disable it
          for this song, or add your own word from the lyrics below and assign it one of the
          existing motions ("flash" points every head straight up at full white).
        </p>
        {Object.keys(keywordMotions).length === 0 ? (
          <p className={styles.empty}>No active triggers for this song.</p>
        ) : (
          <ul className={styles.topicList}>
            {Object.entries(keywordMotions).map(([word, motion]) => (
              <li key={word} className={styles.topicItem}>
                <span className={styles.topicWord}>&ldquo;{word}&rdquo;</span>
                <span className={styles.matchedFile}>{motion}</span>
                <button
                  type="button"
                  className={styles.createImageBtn}
                  onClick={() => removeKeyword(word)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}

        {lyricCandidates.length > 0 && (
          <>
            <p className={styles.sectionHint} style={{ marginTop: 16 }}>
              Add from this song&apos;s lyrics:
            </p>
            <ul className={styles.topicList}>
              {lyricCandidates.map((c) => (
                <li key={c.word} className={styles.topicItem}>
                  <span className={styles.topicTime}>{formatTimestamp(c.start_ms)}</span>
                  <span className={styles.topicWord}>&ldquo;{c.word}&rdquo;</span>
                  <select
                    aria-label={`Motion for ${c.word}`}
                    className={styles.createImageBtn}
                    value={candidateMotions[c.word] ?? 'shake'}
                    onChange={(e) =>
                      setCandidateMotions((prev) => ({ ...prev, [c.word]: e.target.value as MotionType }))
                    }
                  >
                    {MOTIONS.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className={styles.createImageBtn}
                    onClick={() => addKeyword(c.word, candidateMotions[c.word] ?? 'shake')}
                  >
                    Add
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}

        <div className={styles.topicItem} style={{ marginTop: 12 }}>
          <input
            type="text"
            placeholder="Custom word"
            value={newWord}
            onChange={(e) => setNewWord(e.target.value)}
            className={styles.createImageBtn}
            style={{ flex: 1 }}
          />
          <select
            aria-label="Motion for custom word"
            className={styles.createImageBtn}
            value={newMotion}
            onChange={(e) => setNewMotion(e.target.value as MotionType)}
          >
            {MOTIONS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <button
            type="button"
            className={styles.createImageBtn}
            onClick={() => addKeyword(newWord, newMotion)}
          >
            Add
          </button>
        </div>
      </section>

      {promptWord !== null && (
        <div className={styles.promptOverlay} onClick={() => setPromptWord(null)}>
          <div className={styles.promptDialog} onClick={(e) => e.stopPropagation()}>
            <h3 className={styles.promptTitle}>Image prompt for &ldquo;{promptWord}&rdquo;</h3>
            <textarea
              className={styles.promptText}
              readOnly
              value={buildImagePrompt(promptWord)}
              onFocus={(e) => e.target.select()}
            />
            <p className={styles.promptHint}>
              Gemini doesn&apos;t accept the prompt in the link — copy it, then paste it into
              the prompt box on the Gemini page.
            </p>
            <div className={styles.promptActions}>
              <button
                type="button"
                className={styles.createImageBtn}
                onClick={() => copyPrompt(buildImagePrompt(promptWord))}
              >
                {copied ? 'Copied ✓' : 'Copy prompt'}
              </button>
              <button
                type="button"
                className={styles.createImageBtn}
                onClick={() => openExternal(GEMINI_CREATE_URL)}
              >
                Open Gemini
              </button>
              <button
                type="button"
                className={styles.createImageBtn}
                onClick={() => setPromptWord(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
