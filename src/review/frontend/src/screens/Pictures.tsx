import { useEffect, useState } from 'react';
import styles from './Pictures.module.css';

interface ImageSuggestion {
  word: string;
  start_ms: number;
  end_ms: number;
  matched_file: string;
  matched_tag: string;
  image_id?: string;
  score: number;
}

interface ImageTopic {
  word: string;
  start_ms: number;
  end_ms: number;
}

// A Pictures burst or Moving Head accent pinned to an explicit mm:ss
// timestamp, independent of any transcribed lyric word.
interface ManualOccurrence {
  start_ms: number;
  image_id: string;
}

interface ManualTrigger {
  start_ms: number;
  motion: string;
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

// Parses "m:ss" / "mm:ss" (optional fractional seconds, e.g. "1:23.5") into
// milliseconds. Returns null for anything that doesn't match -- callers
// show an inline error rather than silently accepting garbage input.
function parseTimestamp(value: string): number | null {
  const match = value.trim().match(/^(\d+):([0-5]?\d)(?:\.(\d{1,3}))?$/);
  if (!match) return null;
  const minutes = parseInt(match[1], 10);
  const seconds = parseInt(match[2], 10);
  const millis = match[3] ? parseInt(match[3].padEnd(3, '0'), 10) : 0;
  return minutes * 60_000 + seconds * 1_000 + millis;
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
  // image_id currently mid-Replace, or null. Distinct from `uploading`
  // (word-keyed, for the per-occurrence Choose image flow).
  const [replacing, setReplacing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [promptWord, setPromptWord] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [ignored, setIgnored] = useState<Set<string>>(new Set());
  const [shadowWords, setShadowWords] = useState<Set<string>>(new Set());
  const [keywordMotions, setKeywordMotions] = useState<Record<string, string>>({});
  const [candidateMotions, setCandidateMotions] = useState<Record<string, MotionType>>({});
  const [newWord, setNewWord] = useState('');
  const [newMotion, setNewMotion] = useState<MotionType>('shake');
  // occKey -> image_id chosen for that ONE lyric occurrence, distinct from
  // whatever the word's normal fuzzy-tag match resolves to elsewhere.
  const [overrides, setOverrides] = useState<Map<string, string>>(new Map());
  // image_id -> filename, so an override (which only carries an id) can be
  // shown to the user without a round-trip per row.
  const [imageLibrary, setImageLibrary] = useState<Record<string, string>>({});
  // Manual timestamp entries (Extras screen, 2026-08-09) -- pinned by
  // mm:ss, independent of any transcribed lyric word.
  const [manualOccurrences, setManualOccurrences] = useState<ManualOccurrence[]>([]);
  const [manualTriggers, setManualTriggers] = useState<ManualTrigger[]>([]);
  const [newManualPictureTime, setNewManualPictureTime] = useState('');
  const [newManualTriggerTime, setNewManualTriggerTime] = useState('');
  const [newManualMotion, setNewManualMotion] = useState<MotionType>('shake');
  const [manualUploading, setManualUploading] = useState(false);

  useEffect(() => {
    fetch(`/api/v1/songs/${song.song_id}/ignored-images`)
      .then((r) => (r.ok ? r.json() : { occurrences: [] }))
      .then((body) => setIgnored(occKeysFromOccurrences(body.occurrences ?? [])))
      .catch(() => {});
  }, [song.song_id]);

  useEffect(() => {
    fetch(`/api/v1/songs/${song.song_id}/image-overrides`)
      .then((r) => (r.ok ? r.json() : { overrides: [] }))
      .then((body) => {
        const map = new Map<string, string>();
        for (const o of body.overrides ?? []) {
          if (o.word && o.start_ms != null && o.image_id) map.set(occKey(o.word, o.start_ms), o.image_id);
        }
        setOverrides(map);
      })
      .catch(() => {});
  }, [song.song_id]);

  useEffect(() => {
    fetch('/api/v1/images')
      .then((r) => (r.ok ? r.json() : { images: [] }))
      .then((body) => {
        const map: Record<string, string> = {};
        for (const img of body.images ?? []) {
          if (img.id && img.filename) map[img.id] = img.filename;
        }
        setImageLibrary(map);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetch(`/api/v1/songs/${song.song_id}/image-manual-occurrences`)
      .then((r) => (r.ok ? r.json() : { occurrences: [] }))
      .then((body) => setManualOccurrences(body.occurrences ?? []))
      .catch(() => {});
  }, [song.song_id]);

  useEffect(() => {
    fetch(`/api/v1/songs/${song.song_id}/moving-head-timestamps`)
      .then((r) => (r.ok ? r.json() : { triggers: [] }))
      .then((body) => setManualTriggers(body.triggers ?? []))
      .catch(() => {});
  }, [song.song_id]);

  // The row's normal matched_file, unless either (a) this specific
  // occurrence has an override pinning it to a different library image, or
  // (b) the shared library entry itself (rowImageId) was replaced in
  // place -- imageLibrary is refreshed after both a per-occurrence
  // override upload and a library-wide Replace, so a Replace's filename
  // update is picked up here automatically by every row sharing that
  // image_id, not just the row the Replace button was clicked from.
  function displayedFile(word: string, startMs: number, fallback: string, rowImageId?: string): string {
    const overrideId = overrides.get(occKey(word, startMs));
    if (overrideId) return imageLibrary[overrideId] ?? fallback;
    if (rowImageId) return imageLibrary[rowImageId] ?? fallback;
    return fallback;
  }

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
      // The backend also clears any standing per-occurrence override for
      // this word/start_ms (an override always wins over an ignore at
      // export time otherwise) -- mirror that here so the UI doesn't keep
      // showing a stale "Choose image" selection for a row that's now
      // actually unmapped.
      setOverrides((prev) => {
        const next = new Map(prev);
        next.delete(occKey(token, startMs));
        return next;
      });
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
      // Awaited (not fire-and-forget) so it fully completes before the
      // override PUT below starts: both routes independently do a
      // read-session -> modify-one-field -> write-whole-session round trip,
      // so firing them concurrently let the override PUT's write silently
      // clobber this un-ignore with its own stale copy of the ignored list
      // (2026-08-08 user report: occurrence stayed ignored on reload even
      // though the override had visibly saved -- backend now also treats
      // an override as taking priority over a stale ignore regardless, see
      // image_catalog.suggest_images_for_words, but sequencing here removes
      // the race at its source instead of only papering over the result).
      if (ignored.has(occKey(topic.word, topic.start_ms))) await restoreMatch(topic.word, topic.start_ms);
      // Scope the new image to THIS occurrence only -- it's still saved to
      // the shared library under the word's tag (future songs/occurrences
      // can still fuzzy-match it normally), but this specific row won't
      // silently start sharing whatever OTHER occurrences of the same word
      // later match to (2026-08-08: "Choose image" previously affected the
      // word globally despite being laid out per-occurrence).
      const imageId = body?.image?.id;
      const filename = body?.image?.filename;
      if (imageId) {
        const overrideRes = await fetch(`/api/v1/songs/${song.song_id}/image-overrides`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ word: topic.word, start_ms: topic.start_ms, image_id: imageId }),
        }).catch(() => null);
        if (overrideRes?.ok) {
          setOverrides((prev) => new Map(prev).set(occKey(topic.word, topic.start_ms), imageId));
          if (filename) setImageLibrary((prev) => ({ ...prev, [imageId]: filename }));
        } else {
          setError('Image uploaded, but assigning it to this occurrence failed — try Choose image again.');
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    } finally {
      setUploading(null);
    }
  }

  // Overwrites the shared library entry's file in place (same image_id) --
  // every occurrence already matched to it (fuzzy-tag or per-occurrence
  // override) picks up the new image immediately, unlike Choose image
  // above (which scopes to one occurrence via a new separate entry).
  // Intended for fixing a shared asset used across many occurrences
  // (2026-08-08 user request: "sing.png is used quite a bit").
  async function handleReplace(imageId: string, file: File) {
    setReplacing(imageId);
    setError(null);
    try {
      const form = new FormData();
      form.append('image', file);
      const res = await fetch(`/api/v1/images/${imageId}`, { method: 'PUT', body: form });
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Replace failed');
        return;
      }
      const filename = body?.image?.filename;
      if (filename) setImageLibrary((prev) => ({ ...prev, [imageId]: filename }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    } finally {
      setReplacing(null);
    }
  }

  // Uploads a new image and pins it to an explicit mm:ss timestamp,
  // independent of any transcribed lyric word (Extras screen, 2026-08-09).
  // Mirrors handleUpload's upload-then-PUT sequencing, just against the
  // manual-occurrences endpoint (keyed by start_ms, not word+start_ms) and
  // without an ignore to lift (a manual entry was never a lyric match to
  // begin with).
  async function handleManualUpload(startMs: number, file: File) {
    setManualUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('image', file);
      form.append('tag', 'manual');
      const res = await fetch('/api/v1/images', { method: 'POST', body: form });
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Upload failed');
        return;
      }
      const imageId = body?.image?.id;
      const filename = body?.image?.filename;
      if (!imageId) return;
      const putRes = await fetch(`/api/v1/songs/${song.song_id}/image-manual-occurrences`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_ms: startMs, image_id: imageId }),
      }).catch(() => null);
      if (putRes?.ok) {
        setManualOccurrences((prev) => [...prev.filter((o) => o.start_ms !== startMs), { start_ms: startMs, image_id: imageId }]);
        if (filename) setImageLibrary((prev) => ({ ...prev, [imageId]: filename }));
        setNewManualPictureTime('');
      } else {
        setError('Image uploaded, but pinning it to this timestamp failed — try again.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    } finally {
      setManualUploading(false);
    }
  }

  async function removeManualOccurrence(startMs: number) {
    setError(null);
    try {
      const res = await fetch(
        `/api/v1/songs/${song.song_id}/image-manual-occurrences/${startMs}`,
        { method: 'DELETE' },
      );
      if (!res.ok) {
        const body = await res.json();
        setError(body?.error?.message ?? 'Failed to remove');
        return;
      }
      setManualOccurrences((prev) => prev.filter((o) => o.start_ms !== startMs));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    }
  }

  async function addManualTrigger(timeStr: string, motion: MotionType) {
    const startMs = parseTimestamp(timeStr);
    if (startMs === null) {
      setError('Enter a time as m:ss, e.g. 1:23');
      return;
    }
    setError(null);
    try {
      const res = await fetch(`/api/v1/songs/${song.song_id}/moving-head-timestamps`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_ms: startMs, motion }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Failed to add');
        return;
      }
      setManualTriggers(body.triggers ?? []);
      setNewManualTriggerTime('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    }
  }

  async function removeManualTrigger(startMs: number) {
    setError(null);
    try {
      const res = await fetch(
        `/api/v1/songs/${song.song_id}/moving-head-timestamps/${startMs}`,
        { method: 'DELETE' },
      );
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Failed to remove');
        return;
      }
      setManualTriggers(body.triggers ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    }
  }

  const remainingTopics = imageTopics.filter((t) => !uploaded.has(t.word));
  const activeSuggestions = imageSuggestions.filter(
    (s) => !ignored.has(occKey(s.word, s.start_ms)),
  );
  // Unmapped occurrences go back to "Suggested topics" — one row per
  // unmapped occurrence, not deduped by word (each occurrence is unmapped
  // independently now, so other occurrences of the same word may still be
  // mapped and appear in "Already matched"). Deliberately NOT filtered on
  // `uploaded` (word-level) -- resolving one occurrence already removes
  // just that occKey from `ignored` via restoreMatch below, which is
  // enough to drop it from this list; a word-level check here previously
  // hid every other ignored occurrence of the same word the moment ANY
  // one of them got a new image (2026-08-08 user report).
  const ignoredTopics = imageSuggestions.filter(
    (s) => ignored.has(occKey(s.word, s.start_ms)),
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
                <span className={styles.matchedFile}>
                  {displayedFile(s.word, s.start_ms, s.matched_file, s.image_id)}
                </span>
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
                {s.image_id && (
                  <label
                    className={styles.uploadLabel}
                    title="Replace this shared image everywhere it's used, not just this occurrence"
                  >
                    {replacing === s.image_id ? 'Replacing…' : 'Replace'}
                    <input
                      type="file"
                      accept=".gif,.png,.bmp,.jpg,.jpeg"
                      className={styles.uploadInput}
                      disabled={replacing === s.image_id}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file && s.image_id) handleReplace(s.image_id, file);
                        e.target.value = '';
                      }}
                    />
                  </label>
                )}
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
        <h3 className={styles.sectionTitle}>Pictures at a specific time</h3>
        <p className={styles.sectionHint}>
          Pin an image to an exact moment (m:ss) instead of a lyric word — useful for an
          instrumental passage or a word the transcript missed.
        </p>
        {manualOccurrences.length === 0 ? (
          <p className={styles.empty}>No manual timestamps for this song.</p>
        ) : (
          <ul className={styles.topicList}>
            {manualOccurrences.map((o) => (
              <li key={`manual-pic-${o.start_ms}`} className={styles.topicItem}>
                <span className={styles.topicTime}>{formatTimestamp(o.start_ms)}</span>
                <span className={styles.matchedFile}>{imageLibrary[o.image_id] ?? o.image_id}</span>
                <button
                  type="button"
                  aria-label="Remove manual picture"
                  className={styles.createImageBtn}
                  onClick={() => removeManualOccurrence(o.start_ms)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className={styles.topicItem} style={{ marginTop: 12 }}>
          <input
            type="text"
            placeholder="m:ss"
            aria-label="Time for manual picture"
            value={newManualPictureTime}
            onChange={(e) => setNewManualPictureTime(e.target.value)}
            className={styles.createImageBtn}
            style={{ flex: 1 }}
          />
          <label className={styles.uploadLabel}>
            {manualUploading ? 'Uploading…' : 'Choose image'}
            <input
              type="file"
              accept=".gif,.png,.bmp,.jpg,.jpeg"
              className={styles.uploadInput}
              disabled={manualUploading}
              onChange={(e) => {
                const file = e.target.files?.[0];
                const startMs = parseTimestamp(newManualPictureTime);
                if (startMs === null) {
                  setError('Enter a time as m:ss, e.g. 1:23');
                } else if (file) {
                  handleManualUpload(startMs, file);
                }
                e.target.value = '';
              }}
            />
          </label>
        </div>
      </section>

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

        <p className={styles.sectionHint} style={{ marginTop: 16 }}>
          Or trigger an accent at a specific time (m:ss), independent of any lyric word:
        </p>
        {manualTriggers.length > 0 && (
          <ul className={styles.topicList}>
            {manualTriggers.map((t) => (
              <li key={`manual-mh-${t.start_ms}`} className={styles.topicItem}>
                <span className={styles.topicTime}>{formatTimestamp(t.start_ms)}</span>
                <span className={styles.matchedFile}>{t.motion}</span>
                <button
                  type="button"
                  aria-label="Remove manual trigger"
                  className={styles.createImageBtn}
                  onClick={() => removeManualTrigger(t.start_ms)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className={styles.topicItem} style={{ marginTop: 12 }}>
          <input
            type="text"
            placeholder="m:ss"
            aria-label="Time for manual Moving Head trigger"
            value={newManualTriggerTime}
            onChange={(e) => setNewManualTriggerTime(e.target.value)}
            className={styles.createImageBtn}
            style={{ flex: 1 }}
          />
          <select
            aria-label="Motion for manual trigger"
            className={styles.createImageBtn}
            value={newManualMotion}
            onChange={(e) => setNewManualMotion(e.target.value as MotionType)}
          >
            {MOTIONS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
          <button
            type="button"
            aria-label="Add manual trigger"
            className={styles.createImageBtn}
            onClick={() => addManualTrigger(newManualTriggerTime, newManualMotion)}
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
