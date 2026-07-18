import React, { useState } from 'react';
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

interface PicturesScreenProps {
  song: Song;
  imageSuggestions: ImageSuggestion[];
  imageTopics: ImageTopic[];
  onContinue: () => void;
}

function formatTimestamp(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

function buildImagePrompt(word: string): string {
  return `${word.toLowerCase()}, 16x16 bold colors, black background`;
}

// Bing strips query parameters from the image-creator URL on load, so the
// prompt can't be passed in the link — the popup shows it for copy/paste.
const BING_CREATE_URL = 'https://www.bing.com/images/create/ai-image-generator';

async function openExternal(url: string) {
  try {
    const { open } = await import('@tauri-apps/plugin-shell');
    await open(url);
  } catch {
    window.open(url, '_blank');
  }
}

export function Pictures({ song, imageSuggestions, imageTopics, onContinue }: PicturesScreenProps) {
  const [uploaded, setUploaded] = useState<Set<string>>(new Set());
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [promptWord, setPromptWord] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    } finally {
      setUploading(null);
    }
  }

  const remainingTopics = imageTopics.filter((t) => !uploaded.has(t.word));

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
        {remainingTopics.length === 0 ? (
          <p className={styles.empty}>No unmatched topics — nothing to upload.</p>
        ) : (
          <ul className={styles.topicList}>
            {remainingTopics.map((t) => (
              <li key={`${t.word}-${t.start_ms}`} className={styles.topicItem}>
                <span className={styles.topicTime}>{formatTimestamp(t.start_ms)}</span>
                <span className={styles.topicWord}>&ldquo;{t.word}&rdquo;</span>
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
                <button
                  type="button"
                  className={styles.createImageBtn}
                  onClick={() => openCreateImage(t.word)}
                >
                  Create image
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {(imageSuggestions.length > 0 || uploaded.size > 0) && (
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>Already matched</h3>
          <ul className={styles.topicList}>
            {imageSuggestions.map((s, i) => (
              <li key={`matched-${s.word}-${s.start_ms}-${i}`} className={styles.topicItem}>
                <span className={styles.topicTime}>{formatTimestamp(s.start_ms)}</span>
                <span className={styles.topicWord}>&ldquo;{s.word}&rdquo;</span>
                <span className={styles.matchedArrow}>&rarr;</span>
                <span className={styles.matchedFile}>{s.matched_file}</span>
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
                  onClick={() => openCreateImage(s.word)}
                >
                  Create image
                </button>
              </li>
            ))}
            {imageTopics.filter((t) => uploaded.has(t.word)).map((t) => (
              <li key={`uploaded-${t.word}-${t.start_ms}`} className={styles.topicItem}>
                <span className={styles.topicTime}>{formatTimestamp(t.start_ms)}</span>
                <span className={styles.topicWord}>&ldquo;{t.word}&rdquo;</span>
                <span className={styles.matchedArrow}>&rarr;</span>
                <span className={styles.matchedFile}>uploaded</span>
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
                <button
                  type="button"
                  className={styles.createImageBtn}
                  onClick={() => openCreateImage(t.word)}
                >
                  Create image
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

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
              Bing no longer accepts the prompt in the link — copy it, then paste it into the
              prompt box on the Bing page.
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
                onClick={() => openExternal(BING_CREATE_URL)}
              >
                Open Bing
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
